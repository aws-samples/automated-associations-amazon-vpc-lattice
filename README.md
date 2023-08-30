# Amazon VPC Lattice associations automation

This repository implements a solution to automate [Amazon VPC Lattice](https://aws.amazon.com/vpc/lattice/) associations - both VPC and VPC Lattice service - within the same or cross AWS Accounts. The solution focuses in the use of tags in the VPC, VPC Lattice service network, and VPC Lattice service - or and/or [AWS RAM]() share names when working in multi-Account environments - to map resources between each other and create the corresponding associations. The following automations are supported by this solution - in all of the, the tag key `stage` is the one required to automate the corresponding action:

* VPC Lattice VPC and/or service associations anytime the VPC/service's tag is updated.
* Sharing VPC Lattice service network and/or service with allowed AWS Accounts anytime the VPC Lattice service's tag is updated.
* Accept shared VPC Lattice service network and/or service (from allowed AWS Accounts) every minute, and associate them to the corresponding VPC, service, or service network.

In the section **Automations** you have a deeper explanation of each automation. All of them are based on the use of [Amazon EventBridge](https://aws.amazon.com/eventbridge/) to detect changes in the AWS network resources, and [AWS Lambda](https://aws.amazon.com/lambda/) to perform the corresponding actions. 

## Implementation

This solution is based on only 1 [AWS CloudFormation]() file (`solution.yaml`) that builds the following resources:

* Custom resource that stores all the Python functions as ZIP files in an Amazon S3 bucket - to build the different Lambda functions.
* Depending the automation to build, EventBridge rules and Lambda functions will be deployed.

The following inputs will determine which automations are built:

| Name | Description | Allowed Values |
|------|-------------|----------------|
| <a name="VPCLatticeAssociation"></a> | Which VPC Lattice association to automate (from changes in tag "stage"). | `VPC`, `SERVICE`, `BOTH`, `NONE` |

In the section **VPC Lattice common architectures** you will find some examples of multi-Account environments and which specific automations to build in each Account (inputs to include in each CloudFormation deployment) to have the desired functionality.

## Automations

* VPC Lattice VPC associations anytime the VPC's tags are updated.
    * For VPC Lattice service networks in the same AWS Account, the tag `stage` will determine if the association is done or not.
    * For VPC Lattice service networks shared via RAM, the RAM share name will determine if the association is done or not.
    * Given a VPC can only be associated with one VPC Lattice service network, if several ones can be potentially associated only one will be selected randomly (*local* service networks will have preference).
* VPC Lattice service associations anytime the VPC Lattice service's tags are updated.
    * For VPC Lattice service networks in the same AWS Account, the tag `stage` will determine if the association is done or not.
    * For VPC Lattice service networks shared via RAM, the RAM share name will determine if the association is done or not.
    * Several associations are supported, in that case the tag `stage` will require the use of the symbol `+` to separate the different stages - for example *prod+test*.
* Sharing VPC Lattice service 


## VPC Lattice common architectures


## References 