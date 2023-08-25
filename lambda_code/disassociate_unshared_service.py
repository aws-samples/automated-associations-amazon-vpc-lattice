import logging
import os
import json
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

ram_client = boto3.client('ram')
vpc_lattice_client = boto3.client('vpc-lattice')
ssm_client = boto3.client('ssm')

stage_to_network_parameter = os.getevn('PARAMETER_NAME')

def lambda_handler(event, context):
    # We obtain the map of stages and service networks from SSM Parameter
    stage_to_network_dict = json.loads(ssm_client.get_parameter(Name=stage_to_network_parameter)['Parameter']['Value'])
    
    associations = []
    for service_network_arn in stage_to_network_dict.values():
        associations.extend(get_service_associations(service_network_arn))
    logger.info(f'Found service associations {json.dumps(associations, default=str)}')

    service_arns = get_shared_service_arns()
    logger.info(f'Found shared service arns {service_arns}')

    num_associations_deleted = 0
    for association in associations:
        if association['serviceArn'] not in service_arns:
            logger.info(f'Deleting association {json.dumps(associations, default=str)}')
            vpc_lattice_client.delete_service_network_service_association(
                serviceNetworkServiceAssociationIdentifier=association['id']
            )
            num_associations_deleted += 1
    logger.info(f'Deleted {num_associations_deleted} associations.')


def get_service_associations(service_network_identifier):
    associations = []
    paginator = vpc_lattice_client.get_paginator('list_service_network_service_associations')
    iterator = paginator.paginate(
        serviceNetworkIdentifier=service_network_identifier
    )
    for iteration in iterator:
        associations.extend(iteration['items'])
    return associations


def get_shared_service_arns():
    services = []
    paginator = ram_client.get_paginator('list_resources')
    iterator = paginator.paginate(
        resourceOwner='OTHER-ACCOUNTS',
        resourceType='vpc-lattice:Service'
    )
    for iteration in iterator:
        services.extend(iteration['resources'])
    return [s['arn'] for s in services]