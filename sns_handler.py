import boto3
from config import AWS_REGION, SNS_TOPICS

sns = boto3.client('sns', region_name=AWS_REGION)

def send_sns(topic_key, message, subject="StyleLane Alert"):
    topic_arn = SNS_TOPICS[topic_key]
    response = sns.publish(
        TopicArn=topic_arn,
        Subject=subject,
        Message=message
    )
    return response
