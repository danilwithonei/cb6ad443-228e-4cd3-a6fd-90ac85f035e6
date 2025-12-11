import boto3


session = boto3.session.Session()
s3 = session.client(service_name="s3", endpoint_url="https://s3.cloud.ru/bucket-469ae6")

# Создать новый бакет
s3.create_bucket(Bucket="test")
s3.upload_file("./garbage/videos/1.mp4", "test", "1/video.mp4")
s3.upload_file("./garbage/faces/sasha.png", "test", "1/image.png")

# # Удалить несколько объектов
# forDeletion = [{'Key':'object_name'}, {'Key':'script/py_script.py'}]
# response = s3.delete_objects(Bucket='my-bucket', Delete={'Objects': forDeletion})

# # Удалить бакет и все объекты, включая их версии
# s3_resource = boto3.resource(
#    's3', endpoint_url='endpoint_url')
# s3_bucket = s3_resource.Bucket('my-bucket')
# bucket_versioning = s3_resource.BucketVersioning('my-bucket')
# if bucket_versioning.status == 'Enabled':
#    s3_bucket.object_versions.delete()
# else:
#    s3_bucket.objects.all().delete()
#    s3_bucket.delete()
