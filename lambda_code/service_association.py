from functools import lru_cache

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

@lru_cache(maxsize=None)
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
    shared to/created in this account, the first one found will be returned. This is
    because one service network can be associated to one VPC.
    """
    service_networks = list_all_service_networks()
    return next((sn for sn in service_networks if sn['name'] == stage.lower()), None)


def get_stage(event):
    tags = event['detail']['tags']
    for k, v in tags.items():
        if k.lower() == 'stage':
            return v.lower()

def handle_create_tags(event, context):
    # Getting information: VPC Lattice service ARN, stage, and VPC Lattice service network
    service_arn = event['resources'][0]
    stage = get_stage(event)
    service_network = get_service_network_for_stage(stage)

    # Is our VPC Lattice service already associated to a service network?
    # First, check current associations
    associations = vpc_lattice.list_service_network_service_associations(
        serviceIdentifier=service_arn
    )['items'][:]
    # If the service is already associated to the service network we want, all good!
    if stage in [a['serviceNetworkName'] for a in associations]:
        return {
            'statusCode': 200,
            'body': {
                'message': 'Already associated.'
            }
        }

    # Delete association to the previous stage's service network if there was one
    old_stage_associations = [
        a for a in associations
        if a['serviceNetworkName'] in stage_names and a['serviceNetworkName'] != stage
    ]
    delete_service_network_service_associations(old_stage_associations)

    # If we don't find any VPC Lattice service network with the specific stage name, we throw a Exception 
    if service_network is None:
        raise Exception(f'Could not find service network for stage {stage}.')

    # Create association to the corresponding service network
    association = vpc_lattice.create_service_network_service_association(
        serviceIdentifier=service_arn,
        serviceNetworkIdentifier=service_network['id']
    )
    
    logger.info(f'Created association {json.dumps(association, default=str)}')
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Created new association: {json.dumps(association, default=str)}')
        }
    }


def delete_service_network_service_associations(associations):
    for association in associations:
        vpc_lattice.delete_service_network_service_association(
            serviceNetworkServiceAssociationIdentifier=association['id']
        )
        logger.info(f'Deleted association {json.dumps(association, default=str)}')



def handle_delete_tags(event, context):
    """
    Deletes a service's associations with all stage-specific service networks.
    """
    service_arn = event['resources'][0]
    associations = vpc_lattice.list_service_network_service_associations(
        serviceIdentifier=service_arn
    )['items'][:]

    stage_associations = [a for a in associations if a['serviceNetworkName'] in stage_names]
    delete_service_network_service_associations(stage_associations)

    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Deleted associations {json.dumps(stage_associations, default=str)}')
        }
    }


def lambda_handler(event, context):
    logger.info(f'Event: {json.dumps(event)}')
    
    if 'stage' in event['detail']['tags']:
        return handle_create_tags(event, context)
    else:
        return handle_delete_tags(event, context)

    return {
        'statusCode': 400,
        'body': {
            'message': json.dumps(f'Invalid event input.')
        }
    }