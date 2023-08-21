import json
import logging
import time
import sys

from pip._internal import main

# ----- TEMPORAL: UPDATE BOTO3 TO HAVE VPC-LATTICE
main(['install', '-I', '-q', 'boto3', '--target', '/tmp/', '--no-cache-dir', '--disable-pip-version-check'])
sys.path.insert(0,'/tmp/')
# -----
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

vpc_lattice = boto3.client('vpc-lattice')

def list_all_service_networks():
    response = vpc_lattice.list_service_networks()
    service_networks = response['items'][:]
    while 'nextToken' in response:
        response = vpc_lattice.list_service_networks(
            nextToken=response['nextToken']
        )
        service_networks += response['items']
    
    return service_networks

def get_service_network_for_stage(stage):
    """
    In the off-chance that multiple service networks with the same name are
    shared to/created in this account, the first one found with the name matching the stage
    will be returned. This is because a VPC can have one service network
    associated to it.
    """
    service_networks = list_all_service_networks()
    return next((sn for sn in service_networks if sn['name'] == stage.lower()), None)

def get_stage(event):
    tag_changes = event['detail']['requestParameters']['tagSet']['items']
    for tag_change in tag_changes:
        if tag_change['key'].lower() == 'stage':
            return tag_change['value'].lower()

def handle_create_tags(event, context):
    # Getting information: VPC ID, stage (from EventBridge event), and VPC Lattice service network
    vpc_id = event['detail']['requestParameters']['resourcesSet']['items'][0]['resourceId']
    stage = get_stage(event)
    service_network = get_service_network_for_stage(stage)
    
    # Is our VPC already associated to a VPC Lattice service network?
    # First, check current associations of the VPC
    associations = vpc_lattice.list_service_network_vpc_associations(
        vpcIdentifier=vpc_id
    )['items'][:]
    # If the service network is already the one we want to associate, all good!
    for a in associations:
        if stage in a['serviceNetworkName']:
            print()
            return {
                'statusCode': 409,
                'body': {
                    'message': json.dumps(f'Association for stage already exists: {a}.', default=str)
                }
            }
    # Delete association to the previous stage's service network if there was one
    old_stage_associations = [
        a for a in associations
        if a['serviceNetworkName'] != stage
    ]
    delete_service_network_vpc_associations(old_stage_associations)
    
    # If we don't find any VPC Lattice service network with the specific stage name, we throw a Exception 
    if service_network is None:
        raise Exception(f'Could not find service network for stage {stage}.')
    
    # Create association to the corresponding service network
    association = vpc_lattice.create_service_network_vpc_association(
        vpcIdentifier=vpc_id,
        serviceNetworkIdentifier=service_network['id']
    )

    
    logger.info(f'Created association {json.dumps(association, default=str)}')
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Created new association: {association}', default=str)
        }
    }


def handle_delete_tags(event, context):
    """
    Deletes a VPC's association with a stage-specific service network.
    """
    # Getting information: VPC ID, and stage
    vpc_id = event['detail']['requestParameters']['resourcesSet']['items'][0]['resourceId']
    stage = get_stage(event)
    
    # We obtain the current service network associated to the VPC
    associations = vpc_lattice.list_service_network_vpc_associations(
        vpcIdentifier=vpc_id
    )['items']
    stage_associations = [a for a in associations if a['serviceNetworkName'] == stage]
    
    # We remove the VPC association
    delete_service_network_vpc_associations(stage_associations)
    
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Deleted associations {associations}', default=str)
        }
    }

def delete_service_network_vpc_associations(associations):
    for association in associations:
        vpc_lattice.delete_service_network_vpc_association(
            serviceNetworkVpcAssociationIdentifier=association['id']
        )
        logger.info(f'Deleted association {json.dumps(association, default=str)}')
    if len(associations) > 0:
        timeout = time.time() + 60
        while True:
            if time.time() > timeout:
                raise Exception(f'Timed out waiting for previous associations {json.dumps(associations, default=str)} to be deleted')
            for association in associations:
                try:
                    vpc_lattice.get_service_network_vpc_association(
                        serviceNetworkVpcAssociationIdentifier=association['id']
                    )
                    time.sleep(1)
                except vpc_lattice.exceptions.ResourceNotFoundException:
                    time.sleep(1)
                    return
    
def lambda_handler(event, context):
    logger.info(f'Event: {json.dumps(event)}')
    
    print(event)
    event_type = event['detail']['eventName']
    
    if event_type == 'CreateTags':
        return handle_create_tags(event, context)
    elif event_type == 'DeleteTags':
        return handle_delete_tags(event, context)
    
    return {
        'statusCode': 400,
        'body': {
            'message': json.dumps(f'Invalid event input.')
        }
    }