# AWS Infrastructure Plan

This document outlines a comprehensive AWS infrastructure plan based on the provided Docker Compose configuration, addressing high availability, security, and monitoring requirements.

## Task 1: Setting Up a Highly Available Web Application on AWS using ECS

### Architecture Diagram Description

![Architectural Diagram](arch_diagram.png)

The architecture includes:
- Wep Application service containerized with Fargate in multiple AZs
- Application Load Balancer distributing traffic across containers
- PostgreSQL RDS in Multi-AZ configuration
- Auto-scaling based on CPU/memory usage
- VPC with public and private subnets

### Deployment Guide

#### Step 1: Set up the VPC and Networking

```bash
# Create VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=app-vpc}]'

# Create public subnets in 2 AZs
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.1.0/24 --availability-zone us-east-1a --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=public-subnet-1}]'
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.2.0/24 --availability-zone us-east-1b --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=public-subnet-2}]'

# Create private subnets in 2 AZs (for ECS tasks)
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.3.0/24 --availability-zone us-east-1a --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-app-subnet-1}]'
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.4.0/24 --availability-zone us-east-1b --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-app-subnet-2}]'

# Create private subnets in 2 AZs (for RDS)
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.5.0/24 --availability-zone us-east-1a --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-db-subnet-1}]'
aws ec2 create-subnet --vpc-id vpc-12345 --cidr-block 10.0.6.0/24 --availability-zone us-east-1b --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-db-subnet-2}]'
```

#### Step 2: Create RDS Postgres Database (Multi-AZ)

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
    --db-subnet-group-name app-db-subnet-group \
    --db-subnet-group-description "Subnet group for our application DB" \
    --subnet-ids subnet-db1 subnet-db2

# Create RDS instance
aws rds create-db-instance \
    --db-instance-identifier app-postgres \
    --db-instance-class db.t3.small \
    --engine postgres \
    --master-username ${POSTGRES_USER} \
    --master-user-password ${POSTGRES_PASSWORD} \
    --allocated-storage 20 \
    --db-subnet-group-name app-db-subnet-group \
    --vpc-security-group-ids sg-db \
    --backup-retention-period 7 \
    --multi-az \
    --no-publicly-accessible \
    --db-name ${POSTGRES_DB} \
    --storage-encrypted
```

#### Step 3: Create ECS Cluster and Define Task Definition

```bash
# Create ECS cluster
aws ecs create-cluster --cluster-name app-cluster

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

Here's a sample task definition JSON (task-definition.json):

```json
{
  "family": "app-task",
  "networkMode": "awsvpc",
  "executionRoleArn": "arn:aws:iam::account-id:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::account-id:role/app-task-role",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "visitor-book",
      "image": "account-id.dkr.ecr.region.amazonaws.com/visitor-book:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@app-postgres.internal:5432/${POSTGRES_DB}"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/visitor-book",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "visitor-book"
        }
      }
    }
  ]
}
```

#### Step 4: Create ALB and Target Group

```bash
# Create ALB
aws elbv2 create-load-balancer \
    --name app-alb \
    --subnets subnet-public1 subnet-public2 \
    --security-groups sg-alb \
    --scheme internet-facing

# Create target group
aws elbv2 create-target-group \
    --name app-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id vpc-12345 \
    --target-type ip \
    --health-check-path /health \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 2

# Create listener
aws elbv2 create-listener \
    --load-balancer-arn alb-arn \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=acm-cert-arn \
    --default-actions Type=forward,TargetGroupArn=tg-arn
```

#### Step 5: Create ECS Service with Auto Scaling

```bash
# Create ECS service
aws ecs create-service \
    --cluster app-cluster \
    --service-name app-service \
    --task-definition app-task:1 \
    --desired-count 2 \
    --launch-type FARGATE \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-private-app1,subnet-private-app2],securityGroups=[sg-ecs],assignPublicIp=DISABLED}" \
    --load-balancers "targetGroupArn=tg-arn,containerName=visitor-book,containerPort=8000" \
    --health-check-grace-period-seconds 60 \
    --deployment-configuration "deploymentCircuitBreaker={enable=true,rollback=true},maximumPercent=200,minimumHealthyPercent=100" \
    --enable-execute-command

# Configure auto scaling
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/app-cluster/app-service \
    --min-capacity 2 \
    --max-capacity 10

# Create scaling policy based on CPU
aws application-autoscaling put-scaling-policy \
    --policy-name app-cpu-scaling \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/app-cluster/app-service \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

Sample scaling-policy.json:

```json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
  },
  "ScaleOutCooldown": 60,
  "ScaleInCooldown": 60
}
```

### CI/CD Pipeline Description

1. **Source Stage**: Code is committed to a Git repository (GitHub/GitLab/AWS CodeCommit)
2. **Build Stage**:
   - Pull source code
   - Build Docker image using Dockerfile
   - Run unit tests
   - Push image to ECR
3. **Deploy to Staging**:
   - Update ECS task definition with new image
   - Deploy to staging environment
   - Run integration tests
4. **Manual Approval**: Require human approval before production deployment
5. **Deploy to Production**:
   - Update ECS task definition
   - Deploy using blue/green deployment
   - Monitor for any issues
   - Roll back if necessary

AWS services you could use:
- AWS CodePipeline for orchestration
- AWS CodeBuild for building containers
- AWS CodeDeploy for deployments
- Amazon ECR for container registry

## Task 2: Securing an AWS Deployment

### Security Strategy

#### IAM Best Practices

1. **Principle of Least Privilege**:
   - Create specific IAM roles for services
   - Limit permissions to only what's needed
   - No long-term access keys

2. **Example IAM Policies**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    }
  ]
}
```

3. **IAM Role for ECS Tasks**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:region:account-id:secret:app-secrets-*"
    }
  ]
}
```

#### VPC Design

1. **Public Subnets**:
   - Contains ALB
   - Has route to Internet Gateway
   - No direct instance deployment

2. **Private App Subnets**:
   - Contains ECS Fargate tasks
   - No direct internet access
   - Access internet via NAT Gateway
   - Can communicate with RDS

3. **Private DB Subnets**:
   - Contains RDS instances
   - No internet access
   - Only accessible from App subnets

#### Security Group Rules

1. **ALB Security Group**:
```
Inbound:
- HTTPS (443) from 0.0.0.0/0
- HTTP (80) from 0.0.0.0/0 (redirect to HTTPS)

Outbound:
- Allow only to ECS Security Group on port 8000
```

2. **ECS Security Group**:
```
Inbound:
- Port 8000 from ALB Security Group only

Outbound:
- HTTPS (443) to 0.0.0.0/0 (for Application)
- PostgreSQL (5432) to RDS Security Group
```

3. **RDS Security Group**:
```
Inbound:
- PostgreSQL (5432) from ECS Security Group only

Outbound:
- No outbound rules needed
```

#### S3 Bucket Security

1. **Block Public Access**:
```bash
aws s3api put-public-access-block \
    --bucket app-bucket \
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

2. **Bucket Policy to Enforce Encryption**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUnencryptedObjectUploads",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::app-bucket/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "AES256"
        }
      }
    }
  ]
}
```

#### Data Encryption Strategy

1. **Data at Rest**:
   - RDS storage encryption enabled
   - S3 server-side encryption
   - EBS volume encryption for any attached volumes

2. **Data in Transit**:
   - HTTPS for all external traffic
   - TLS for database connections
   - AWS PrivateLink for service-to-service communication

3. **Secrets Management**:
   - Use AWS Secrets Manager for database credentials
   - Inject secrets into ECS tasks during startup
   - Rotate secrets regularly

## Task 3: Logging and Centralized Monitoring

### Log Management Strategy

#### CloudWatch Logs Configuration for ECS

Enable CloudWatch Logs for ECS containers:

```json
"logConfiguration": {
  "logDriver": "awslogs",
  "options": {
    "awslogs-group": "/ecs/visitor-book",
    "awslogs-region": "us-east-1",
    "awslogs-stream-prefix": "visitor-book"
  }
}
```

Create the log group with retention:

```bash
aws logs create-log-group --log-group-name /ecs/visitor-book
aws logs put-retention-policy --log-group-name /ecs/visitor-book --retention-in-days 30
```

#### Structured Logging

Example of structured logging in the application:

```python
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_event(event_type, data):
    log_entry = {
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    }
    print(json.dumps(log_entry))
```

#### CloudTrail Configuration

```bash
# Create CloudTrail trail
aws cloudtrail create-trail \
    --name app-trail \
    --s3-bucket-name app-audit-logs \
    --is-multi-region-trail \
    --enable-log-file-validation \
    --kms-key-id alias/aws/s3

# Enable the trail
aws cloudtrail start-logging --name app-trail

# Enable CloudTrail Insights
aws cloudtrail put-insight-selectors \
    --trail-name app-trail \
    --insight-selectors '[{"InsightType": "ApiCallRateInsight"},{"InsightType": "ApiErrorRateInsight"}]'
```

#### CloudWatch Alarms

```bash
# Create alarm for API error rate
aws cloudwatch put-metric-alarm \
    --alarm-name api-high-error-rate \
    --alarm-description "Alert when API error rate exceeds threshold" \
    --metric-name 4XXError \
    --namespace AWS/ApplicationELB \
    --statistic Sum \
    --period 60 \
    --threshold 10 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --dimensions Name=LoadBalancer,Value=app-alb \
    --alarm-actions arn:aws:sns:region:account-id:app-alerts

# Create alarm for ECS CPU utilization
aws cloudwatch put-metric-alarm \
    --alarm-name ecs-high-cpu \
    --alarm-description "Alert when ECS CPU is consistently high" \
    --metric-name CPUUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 85 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 3 \
    --dimensions Name=ClusterName,Value=app-cluster Name=ServiceName,Value=app-service \
    --alarm-actions arn:aws:sns:region:account-id:app-alerts
```

#### OpenSearch/ELK Stack for Centralized Logging

1. **OpenSearch Setup**:

```bash
# Create OpenSearch domain
aws opensearch create-domain \
    --domain-name app-logs \
    --engine-version OpenSearch_1.3 \
    --cluster-config InstanceType=r6g.large.search,InstanceCount=2 \
    --ebs-options EBSEnabled=true,VolumeType=gp3,VolumeSize=100 \
    --node-to-node-encryption-options Enabled=true \
    --encryption-at-rest-options Enabled=true \
    --domain-endpoint-options EnforceHTTPS=true \
    --advanced-security-options Enabled=true,InternalUserDatabaseEnabled=true,MasterUserOptions='{MasterUserName=admin,MasterUserPassword=Password123!}' \
    --access-policies '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"arn:aws:iam::account-id:role/LogDeliveryRole"},"Action":"es:*","Resource":"arn:aws:es:region:account-id:domain/app-logs/*"}]}'
```

2. **Set up Log Subscription Filter**:

```bash
# Create IAM role for log delivery
aws iam create-role \
    --role-name LogDeliveryRole \
    --assume-role-policy-document file://trust-policy.json

# Put subscription filter
aws logs put-subscription-filter \
    --log-group-name /ecs/visitor-book\
    --filter-name app-logs-filter \
    --filter-pattern "" \
    --destination-arn arn:aws:lambda:region:account-id:function:LogsToOpenSearch
```
