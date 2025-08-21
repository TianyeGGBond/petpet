import os
import json
import uuid
import boto3

from PIL import Image

processed_bucket = os.getenv('processed_bucket')
if not processed_bucket:
    raise RuntimeError("Missing env var: processed_bucket / PROCESSED_BUCKET")

ddb_table_name = os.getenv('ddb_table_name', 'UserEmails')
step_fn_arn = os.getenv('step_fn_arn')
if not step_fn_arn:
    raise RuntimeError("Missing env var: step_fn_arn")

s3_client = boto3.client('s3')
sf_client = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
email_table = dynamodb.Table(ddb_table_name)

def get_user_emails():
    resp = email_table.scan()
    return [item["email"] for item in resp.get("Items", [])]


def lambda_handler(event, context):
	print(event)
	
	# get bucket and object key from event object
	source_bucket = event['Records'][0]['s3']['bucket']['name']
	key = event['Records'][0]['s3']['object']['key']
	
	# Generate a temp name, and set location for our original image
	object_key = str(uuid.uuid4()) + '-' + key
	img_download_path = '/tmp/{}'.format(object_key)
	
	# Download the source image from S3 to temp location within execution environment
	with open(img_download_path,'wb') as img_file:
		s3_client.download_fileobj(source_bucket, key, img_file)
		
	# Biggify the pixels and store temp pixelated versions
	pixelate((8,8), img_download_path, '/tmp/pixelated-8x8-{}'.format(object_key) )
	pixelate((16,16), img_download_path, '/tmp/pixelated-16x16-{}'.format(object_key) )
	pixelate((32,32), img_download_path, '/tmp/pixelated-32x32-{}'.format(object_key) )
	pixelate((48,48), img_download_path, '/tmp/pixelated-48x48-{}'.format(object_key) )
	pixelate((64,64), img_download_path, '/tmp/pixelated-64x64-{}'.format(object_key) )
	
	# uploading the pixelated version to destination bucket
	upload_key = 'pixelated-{}'.format(object_key)
	s3_client.upload_file('/tmp/pixelated-8x8-{}'.format(object_key), processed_bucket,'pixelated-8x8-{}'.format(key))
	s3_client.upload_file('/tmp/pixelated-16x16-{}'.format(object_key), processed_bucket,'pixelated-16x16-{}'.format(key))
	s3_client.upload_file('/tmp/pixelated-32x32-{}'.format(object_key), processed_bucket,'pixelated-32x32-{}'.format(key))
	s3_client.upload_file('/tmp/pixelated-48x48-{}'.format(object_key), processed_bucket,'pixelated-48x48-{}'.format(key))
	s3_client.upload_file('/tmp/pixelated-64x64-{}'.format(object_key), processed_bucket,'pixelated-64x64-{}'.format(key))

	emails = get_user_emails()
	print("Recipients:", emails)

	message = f"Your image {key} has been processed successfully!"
	for email in emails:
		payload = {"email": email, "message": message, "waitSeconds": 0}
		sf_client.start_execution(stateMachineArn=step_fn_arn, input=json.dumps(payload))
		print(f"StepFunctions started for {email}")

	return {"statusCode": 200, "body": json.dumps({"status": "ok"})}

def pixelate(pixelsize, image_path, pixelated_img_path):
	img = Image.open(image_path)
	temp_img = img.resize(pixelsize, Image.BILINEAR)
	new_img = temp_img.resize(img.size, Image.NEAREST)
	new_img.save(pixelated_img_path)
	
	
	