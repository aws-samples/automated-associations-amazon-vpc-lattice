from functools import lru_cache

import json
import logging
import time
import sys
import os

from pip._internal import main

# ----- TEMPORAL: UPDATE BOTO3 TO HAVE VPC-LATTICE
main(['install', '-I', '-q', 'boto3', '--target', '/tmp/', '--no-cache-dir', '--disable-pip-version-check'])
sys.path.insert(0,'/tmp/')
# -----
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

vpc_lattice = boto3.client('vpc-lattice')
ssm = boto3.client('ssm')

parameter_name = os.environ.get("PARAMETER_NAME")

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

def get_current_stage():
    return ssm.get_parameter(Name=parameter_name)['Parameter']['Value']

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

    # If there's already an association to a Service Network, we remove that association
    current_stage = get_current_stage()
    if current_stage != ' ':
        old_stage_associations = [
            a for a in associations
            if a['serviceNetworkName'] == current_stage
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
    # We update the parameter with the new stage
    udpate_parameter = ssm.put_parameter(
        Name = parameter_name,
        Value = stage,
        Overwrite=True
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

    # We get current stage
    current_stage = get_current_stage()
    # We obtain the associations
    stage_associations = [a for a in associations if a['serviceNetworkName'] == current_stage]
    delete_service_network_service_associations(stage_associations)

    # We update the parameter with an 'empty stage'
    udpate_parameter = ssm.put_parameter(
        Name = parameter_name,
        Value = ' ',
        Overwrite=True
    )

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