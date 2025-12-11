import os
import boto3
import shutil
from pathlib import Path


class S3Connection:
    def __init__(self, endpoint_url: str, bucket: str):
        self.session = boto3.session.Session()
        self.client = self.session.client(service_name="s3", endpoint_url=endpoint_url)
        self.bucket: str = bucket
        pass

    def download_file(self, s3_file_path: str, local_file_path: str, bucket: str | None = None) -> str:
        Path(local_file_path).mkdir(parents=True, exist_ok=True)
        local_file_path = os.path.join(local_file_path, os.path.basename(s3_file_path))
        self.client.download_file(
            Bucket=bucket or self.bucket,
            Key=s3_file_path,
            Filename=local_file_path,
        )
        return local_file_path

    def upload_file(
        self,
        local_file_path: str,
        s3_file_path: str,
        bucket: str | None = None,
        delete_local_file_path: bool = False,
    ):
        s3_file_path = os.path.join(s3_file_path, os.path.basename(local_file_path))

        self.client.upload_file(
            local_file_path,
            bucket or self.bucket,
            s3_file_path,
        )
        if delete_local_file_path:
            shutil.rmtree(Path(local_file_path).parent)
