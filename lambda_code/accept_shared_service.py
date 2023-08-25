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

allowlist_str = os.getenv('ALLOWED_ACCOUNTS') or ''
allowlist = [a.strip() for a in allowlist_str.split(',')]
allowlist_enabled = 'ALL' not in allowlist

stage_to_network_parameter = os.getenv("PARAMETER_NAME")
stage_names_env = os.getenv('STAGE_NAMES') or ''
stage_names = [k.strip().lower() for k in stage_names_env.split(',')]
stage_to_network_dict = {}

my_account = os.getenv("MY_ACCOUNT")

def lambda_handler(event, context):
    """
    Performs 2 actions:
    1. Accepts resource share invitations that are named after one of the permitted
    stage names and are sent by an allowlisted account.
    2. For every accepted resource share that is named after one of the permitted
    stage names and is sent by an allowlisted account, associates that share's
    services to the appropriate service network.
    
    Note: if you manually delete a ServiceNetworkServiceAssociation without
    deleting the RAM share, this Lambda Function will recreate the association.
    """
    logger.info(f'Received event {event} and context {context}')
    set_stage_to_network_dict()
    invitations = get_all_pending_resource_share_invitations()
    logger.info(f'Found invitations {invitations}')
    
    for invitation in invitations:
        accept_pending_resource_share_invitation(invitation)
    associate_services_from_accepted_resource_shares()
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed all pending invitations.')
    }


def set_stage_to_network_dict():
    global stage_to_network_dict
    
    all_service_networks = get_all_service_networks()
    
    for sn in all_service_networks:
        sn_account = sn['arn'].split(':')[4]
        if sn_account == my_account:
            tags = vpc_lattice_client.list_tags_for_resource(resourceArn=sn['arn'])['tags']
            if 'stage' in tags.keys():
                if tags['stage'] in stage_names:
                    stage_to_network_dict[tags['stage']] = sn['arn']
    
    logger.info(f'Set stage to network dict {stage_to_network_dict}')

    # We update the parameter with the obtained map: Stage: Service Network
    udpate_parameter = ssm_client.put_parameter(
        Name = stage_to_network_parameter,
        Value = json.dumps(stage_to_network_dict),
        Overwrite=True
    )

def get_all_service_networks():
    service_networks = []
    paginator = vpc_lattice_client.get_paginator('list_service_networks')
    for page in paginator.paginate():
        service_networks.extend(page['items'])
    return service_networks

def get_all_pending_resource_share_invitations():
    invitations = []
    paginator = ram_client.get_paginator('get_resource_share_invitations')
    for page in paginator.paginate():
        invitations.extend(page['resourceShareInvitations'])
    return [inv for inv in invitations if inv['status'] == 'PENDING']

def accept_pending_resource_share_invitation(invitation):
    share_name = invitation['resourceShareName']
    share_arn = invitation['resourceShareArn']
    share_sender_account = invitation['senderAccountId']
    logger.info(f"Processing Resource Share Invitation {share_arn}, named {share_name}, from {share_sender_account}")
    
    if allowlist_enabled and share_sender_account not in allowlist:
        logger.info(f'Share Invitation sender is not in allowlist. Ignoring Share Invitation {share_arn}.')
        return
    
    if share_name not in stage_names:
        logger.info(f'Share Invitation name does not match expected pattern, expected one of {stage_names}. Ignoring Share Invitation {share_arn}.')
        return
    
    logger.info(f'Accepting Resource Share Invitation {share_arn}.')
    accepted_share = ram_client.accept_resource_share_invitation(
        resourceShareInvitationArn=invitation['resourceShareInvitationArn']
    )

def associate_services_from_accepted_resource_shares():
    shares = []
    paginator = ram_client.get_paginator('get_resource_shares')
    for page in paginator.paginate(
        resourceOwner='OTHER-ACCOUNTS',
        resourceShareStatus='ACTIVE'
    ):
        shares.extend(page['resourceShares'])

    logger.info(f'Found existing resource shares: {shares}')
    for share in shares:
        associate_services_from_accepted_resource_share(share)


def associate_services_from_accepted_resource_share(share):
    share_name = share['name']
    share_arn = share['resourceShareArn']
    share_sender_account = share['owningAccountId']
    logger.info(f"Processing Accepted Resource Share {share_arn}, named {share_name}, from {share_sender_account}")
    
    
    if allowlist_enabled and share_sender_account not in allowlist:
        logger.info(f'Share sender is not in allowlist. Ignoring Share {share_arn}.')
        return
    
    if share_name not in stage_names:
        logger.info(f'Share name does not match expected pattern, expected one of {stage_names}. Ignoring Share {share_arn}.')
        return
    
    services = get_shared_services(share)
    logger.info(f'Found services in resource share {services}')    
    
    service_network_arn = stage_to_network_dict[share_name]
    
    for service in services:
        create_association_if_not_associated(service_network_arn, service['arn'], share_name)


def get_shared_services(resource_share):
    attempts = 0
    services = []
    while (len(services) == 0 and attempts < 5):
        attempts += 1
        services = ram_client.list_resources(
            resourceShareArns=[resource_share['resourceShareArn']],
            resourceOwner='OTHER-ACCOUNTS',
            resourceType='vpc-lattice:Service'
        )['resources']
        time.sleep(1)
    return services


def create_association_if_not_associated(
    service_network_identifier,
    service_identifier,
    share_name
):
    existing_associations = vpc_lattice_client.list_service_network_service_associations(
        serviceNetworkIdentifier=service_network_identifier,
        serviceIdentifier=service_identifier
    )['items']
    if (len(existing_associations) == 0):
        logger.info(f'Associating Service {service_identifier} to {share_name} Service Network {service_network_identifier}')
        vpc_lattice_client.create_service_network_service_association(
            serviceNetworkIdentifier=service_network_identifier,
            serviceIdentifier=service_identifier
        )