# Amazon VPC Lattice associations automation

This repository implements a solution to automate [Amazon VPC Lattice](https://aws.amazon.com/vpc/lattice/) associations - both VPC and VPC Lattice service - within the same or cross AWS Accounts. The solution focuses in the use of tags in the VPC, VPC Lattice service network, and VPC Lattice service - or and/or [AWS RAM](https://aws.amazon.com/ram/) share names when working in multi-Account environments - to map resources between each other and create the corresponding associations. The following automations are supported by this solution - in all of the, the tag key `stage` is the one required to automate the corresponding action:

* VPC Lattice VPC and/or service associations anytime the VPC/service's tag is updated.
* Sharing VPC Lattice service network and/or service with allowed AWS Accounts anytime the VPC Lattice service's tag is updated.
* Accept shared VPC Lattice service network and/or service (from allowed AWS Accounts) every minute, and associate them to the corresponding VPC, service, or service network.

In the section **Automations** you have a deeper explanation of each automation. All of them are based on the use of [Amazon EventBridge](https://aws.amazon.com/eventbridge/) to detect changes in the AWS network resources, and [AWS Lambda](https://aws.amazon.com/lambda/) to perform the corresponding actions. 

## Implementation

This solution is based on a single [AWS CloudFormation](https://aws.amazon.com/cloudformation/) file (`solution.yaml`) that builds the following resources:

* Custom resource that stores all the Python functions as ZIP files in an Amazon S3 bucket - to build the different Lambda functions.
* Depending the automation to build, EventBridge rules and Lambda functions will be deployed.

The following inputs will determine which automations are built:

| Name | Description | Allowed Values |
|------|-------------|----------------|
| **VPCLatticeAssociation** | Which VPC Lattice association to automate (from changes in tag `stage`). | `VPC` - `SERVICE` - `BOTH` - `NONE` |
| **ShareAutomation** | Which VPC Lattice resource you want to share (from changes in tag `stage`) | `SERVICE_NETWORK` - `SERVICE` - `BOTH` - `NONE` |
| **ShareAutomationAllowedAccounts** | *If automating VPC Lattice RAM share* List of AWS Accounts to share your resources, divided by comma (Account1,Account2) |  |
| **ShareAutomationAllowedAccounts** | *If automating VPC Lattice RAM share* Provide list of stages allowed to share, divided by comma (stage1,stage2) |  |
| **AcceptShareAutomation** | Which VPC Lattice resource (shared with you) you want to accept. | `SERVICE_NETWORK` - `SERVICE` - `BOTH` - `NONE` |
| **AcceptShareAutomationAllowedAccounts** | *If automating RAM share acceptance* Provide list of AWS Accounts to accept resources shared, divided by comma (Account1,Account2) |  |
| **AcceptShareAutomationAllowedStages** | *If automating RAM share acceptance* Provide list of stages allowed to accept shared resources, divided by comma (stage1,stage2) |  |

In the section **VPC Lattice common architectures** you will find some examples of multi-Account environments and which specific automations to build in each Account (inputs to include in each CloudFormation deployment) to have the desired functionality.

## Automations

### VPC Lattice VPC association

In this automation, the EventBridge rule will obtain changes in VPC tags. Once the tag `stage` is created/updated/removed from any of the VPCs in the Account, the following actions will be automated by a Lambda function:

* Scan all the VPC Lattice service networks in the Account (either owned or shared) and determine which ones share the same *stage*.
    * For service networks owned by the same Account, the tag `stage` will be checked.
    * For service networks shared via RAM, the RAM share name will be checked. This name should be similar to the key of the VPC tag `stage`.
* Given a VPC can only be associated with one service network, if several ones are scanned, the one to be associated will be selected randomly (service networks owned by the same AWS Account will be preferred).
* Updating the `stage` tag will remove the current association (if exists), and create a new one - if any service network with the same `stage` tag/RAM share name exits.
* Removing the `stage` tag will remove the association.

### VPC Lattice service association

In this automation, the EventBridge rule will obtain changes in VPC Lattice service tags. Once the tag `stage` is created/updated/removed from any of the services in the Account, the following actions will be automated by a Lambda function:

* Scan all the VPC Lattice service networks in the Account (either owned or shared) and determine which ones share the same *stage*.
    * For service networks owned by the same Account, the tag `stage` will be checked.
    * For service networks shared via RAM, the RAM share name will be checked. This name should be similar to the key of the VPC tag `stage`.
* As a VPC Lattice service can be associated with multiple service networks, the association will be created with all the service networks scanned.
* Several stages are also supported: the tag `stage` will require the use of the symbol `+` to separate the different stages - for example *prod+test*.
* Updating the `stage` tag will remove the current association (if exists), and create a new one - if any service network with the same `stage` tag/RAM share name exits.
* Removing the `stage` tag will remove the association.
* An [AWS Systems Manager](https://aws.amazon.com/systems-manager/) Parameter is used to store the latest set of stages that are associated with a specific service.

### VPC Lattice service and service network RAM share

In this automation, the EventBridge rule will obtain changes in VPC Lattice service or service network tags. You can define a list of AWS Account and stages allowed for the resource share - as an extra step of control. Once the tag `stage` is created/updated/removed from any of the resources in the Account, the following actions will be automated by a Lambda function:

* If the `stage` tag configured is part of the allowed stages, the tagged resource (VPC Lattice service or service network) is shared using RAM to those AWS Accounts configured in the allowed Accounts list.
* The name of the RAM share will be the value of the `stage` tag, so the stage information is shared between Accounts.
* Update the `stage` tag will remove the current RAM share (if exits), and create a new one - if the new stage value is allowed.
* Removing the `stage` tag will remove the RAM share.

### Accepting VPC Lattice service shared with the Account and creating service associations

For this automation, two [EventBridge scheduler](https://docs.aws.amazon.com/eventbridge/latest/userguide/scheduler.html) is used to invoke two Lambda functions every 1 - 2 minutes to perform the automations. You can change the periodicity of the schedulers by updating the `solution.yaml` file.

* One of the Lambda functions will check if there's any VPC Lattice service associated with the AWS Account, to accept the RAM share (if the sender Account is allowlisted). Once the resource has been accepted, it will check RAM share's name and map it to any VPC Lattice service network with the same `stage` tag value.
* The other Lambda function *cleans* associations of unshared VPC Lattice services. Given the association will still be in-place even if the resource's share has been removed, the function will check which VPC Lattice service associations belong to VPC Lattice services that are no longer available in the AWS Account, and it will remove them.

## VPC Lattice multi-AWS Account architectures

### Centralized VPC Lattice service networks

In this model, the VPC Lattice service networks are owned by a central AWS Account, which is the one in charge of controlling how the associations are built. The automation to build in each AWS Account is the following one:

* *Consumer AWS Accounts* - these Accounts will simply create VPC Lattice VPC associations to shared service networks.

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `VPC` |
| **ShareAutomation** | `NONE` |

* *Central AWS Account* - the central AWS Account will be in charge of sharing the VPC Lattice service networks (with allowed Accounts), and alternatively create VPC Lattice service associations if VPC Lattice services where shared with it.

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `SERVICE` |
| **ShareAutomation** | `SERVICE_NETWORK` |
| **ShareAutomationAllowedAccounts** | *List of AWS Accounts to share your resources, divided by comma (Account1,Account2)* |
| **ShareAutomationAllowedAccounts** | *List of stages allowed to share, divided by comma (stage1,stage2)* |
| **AcceptShareAutomation** | `SERVICE` |
| **AcceptShareAutomationAllowedAccounts** | *List of AWS Accounts to accept resources shared, divided by comma (Account1,Account2)* |
| **AcceptShareAutomationAllowedStages** | *List of stages allowed to accept shared resources, divided by comma (stage1,stage2)* |

* *Provider AWS Accounts* - these Accounts will share their VPC Lattice services with the central Account, plus also creating VPC Lattice service associations if VPC Lattice service networks were shared with them (from the Central Account).

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `SERVICE` |
| **ShareAutomation** | `SERVICE` |
| **ShareAutomationAllowedAccounts** | *Central AWS Account* |
| **ShareAutomationAllowedAccounts** | *List of stages allowed to share, divided by comma (stage1,stage2)* |
| **AcceptShareAutomation** | `SERVICE` |
| **AcceptShareAutomationAllowedAccounts** | *Central AWS Account* |
| **AcceptShareAutomationAllowedStages** | *List of stages allowed to accept shared resources, divided by comma (stage1,stage2)* |

* *Consumer & Provider AWS Account* - it can happen than a Spoke Account is both consuming services from VPC Lattice (VPC association) and creating VPC Lattice services (service association).

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `BOTH` |
| **ShareAutomation** | `SERVICE` |
| **ShareAutomationAllowedAccounts** | *Central AWS Account* |
| **ShareAutomationAllowedAccounts** | *List of stages allowed to share, divided by comma (stage1,stage2)* |
| **AcceptShareAutomation** | `SERVICE` |
| **AcceptShareAutomationAllowedAccounts** | *Central AWS Account* |
| **AcceptShareAutomationAllowedStages** | *List of stages allowed to accept shared resources, divided by comma (stage1,stage2)* |

![CentralizedServiceNetworks](/images/centralized_service_network.png)

### Distributed VPC Lattice service networks

In this model, the VPC Lattice service networks are owned by the spoke AWS Accounts that want to consume VPC Lattice services (each Spoke will have its own service network). Depending the role of the AWS Account, the automation to build will be the following one:

* *Consumer AWS Accounts* - these Accounts will simply create VPC Lattice service associations to shared VPC Lattice services. In addition, they can automate VPC associations if those were not created when the VPC and VPC Lattice service network were built.

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `BOTH` |
| **ShareAutomation** | `NONE` |
| **AcceptShareAutomation** | `SERVICE` |
| **AcceptShareAutomationAllowedAccounts** | *List of AWS Accounts to accept resources shared, divided by comma (Account1,Account2)* |
| **AcceptShareAutomationAllowedStages** | *List of stages allowed to accept shared resources, divided by comma (stage1,stage2)* |

* *Provider AWS Accounts* - these Accounts will share their VPC Lattice services with the consumer AWS Accounts.

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `NONE` |
| **ShareAutomation** | `SERVICE` |
| **ShareAutomationAllowedAccounts** | *List of AWS Accounts to share your resources, divided by comma (Account1,Account2)* |
| **ShareAutomationAllowedAccounts** | *List of stages allowed to share, divided by comma (stage1,stage2)* |
| **AcceptShareAutomation** | `NONE` |

* *Consumer & Provider AWS Account* - it can happen than an Account is both consuming services from VPC Lattice (VPC association) and creating VPC Lattice services (service association).

| Variable | Value |
|----------|-------|
| **VPCLatticeAssociation** | `BOTH` |
| **ShareAutomation** | `SERVICE` |
| **ShareAutomationAllowedAccounts** | *List of AWS Accounts to share your resources, divided by comma (Account1,Account2)* |
| **ShareAutomationAllowedAccounts** | *List of stages allowed to share, divided by comma (stage1,stage2)* |
| **AcceptShareAutomation** | `SERVICE` |
| **AcceptShareAutomationAllowedAccounts** | *List of AWS Accounts to accept resources shared, divided by comma (Account1,Account2)* |
| **AcceptShareAutomationAllowedStages** | *List of stages allowed to accept shared resources, divided by comma (stage1,stage2)* |

![DistributedServiceNetworks](/images/distributed_service_network.png)

<!-- ## References  -->
