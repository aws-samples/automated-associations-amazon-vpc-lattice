import json
import boto3
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

network_admin_account_id = os.getenv('NETWORK_ADMIN_ACCOUNT_ID')
if network_admin_account_id is None:
    raise Exception('Missing NETWORK_ADMIN_ACCOUNT_ID environment variable!')

stage_names_env = os.getenv('STAGE_NAMES') or ''
stage_names = [k.strip().lower() for k in stage_names_env.split(',')]

ram = boto3.client('ram')

def get_new_stage(event):
    tags = event['detail']['tags']
    for k, v in tags.items():
        if k.lower() == 'stage':
            return v.lower()


def handle_create_tags(event, context):
    """
    Delete's a service's existing stage-based resource shares and creates
    a new one with the new stage name.
    """
    service_arn = event['resources'][0]
    stage = get_new_stage(event)

    existing_shares = ram.get_resource_shares(
        resourceOwner='SELF',
        tagFilters=[{
            'tagKey': 'serviceId',
            'tagValues': [service_arn.split('/')[-1]]
        }]
    )['resourceShares']
              
    already_shared = False
    for share in existing_shares:
        if share['name'] == stage and share['status'] in ['PENDING', 'ACTIVE']:
            already_shared = True
        elif share['name'] in stage_names:
            ram.delete_resource_share(
                resourceShareArn=share['resourceShareArn']
            )
              
    if already_shared:
        return {
            'statusCode': 200,
            'body': {
                'message': 'Already shared.'
            }
        }
                  
    share = ram.create_resource_share(
        name=stage,
        principals=[network_admin_account_id],
        resourceArns=[service_arn],
        tags=[{
            'key': 'serviceId',
            'value': service_arn.split('/')[-1]
        }]
    )
    logger.info(f'Created new resource share {json.dumps(share, default=str)}')
    
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Created new resource share: {json.dumps(share, default=str)}')
        }
    }


def handle_delete_tags(event, context):
    """
    Deletes a service's stage-based resource shares.
     """
    service_arn = event['resources'][0]
    existing_shares = ram.get_resource_shares(
        resourceOwner='SELF',
        tagFilters=[{
            'tagKey': 'serviceId',
            'tagValues': [service_arn.split('/')[-1]]
        }]
    )['resourceShares']
              
    shares_to_delete = [s for s in existing_shares if s['status'] not in ['DELETED', 'DELETING']]
              
    for share in shares_to_delete:
        if share['name'] in stage_names:
            ram.delete_resource_share(
                resourceShareArn=share['resourceShareArn']
            )

    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps(f'Deleted resource shares {json.dumps(shares_to_delete, default=str)}')
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