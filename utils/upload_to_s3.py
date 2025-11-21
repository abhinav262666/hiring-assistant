import uuid

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from settings import senv

logger = senv.backend_logger


class S3UploadService:
    """Service for uploading files to Amazon S3."""

    def __init__(self):
        if boto3 is None:
            raise ImportError(
                "boto3 is not installed. Please install it to use S3 upload functionality."
            )

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=getattr(senv, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(senv, "AWS_SECRET_ACCESS_KEY", None),
            region_name=getattr(senv, "AWS_REGION", "us-east-1"),
        )
        self.bucket_name = getattr(senv, "S3_BUCKET_NAME", None)

        if not self.bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set")

    def upload_file(
        self, file_content: bytes, filename: str, content_type: str = None
    ) -> str:
        """
        Upload file to S3 and return the URL.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            content_type: MIME type (optional, will be inferred if not provided)

        Returns:
            Public URL of the uploaded file

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate unique filename to avoid conflicts
            file_extension = filename.split(".")[-1] if "." in filename else ""
            unique_filename = f"{uuid.uuid4()}.{file_extension}"

            # Determine content type
            if not content_type:
                if filename.lower().endswith(".pdf"):
                    content_type = "application/pdf"
                elif filename.lower().endswith(".txt"):
                    content_type = "text/plain"
                elif filename.lower().endswith(".doc"):
                    content_type = "application/msword"
                elif filename.lower().endswith(".docx"):
                    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                else:
                    content_type = "application/octet-stream"

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=unique_filename,
                Body=file_content,
                ContentType=content_type,
                ACL="public-read",  # Make file publicly accessible
            )

            # Generate public URL
            file_url = f"https://{self.bucket_name}.s3.amazonaws.com/{unique_filename}"

            logger.info(f"Successfully uploaded file {filename} to S3: {file_url}")
            return file_url

        except ClientError as e:
            error_msg = f"Failed to upload file to S3: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error uploading file to S3: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def delete_file(self, file_url: str) -> bool:
        """
        Delete file from S3.

        Args:
            file_url: S3 URL of the file to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract key from URL
            # URL format: https://bucket-name.s3.amazonaws.com/filename
            key = file_url.split("/")[-1]

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

            logger.info(f"Successfully deleted file from S3: {file_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file from S3: {str(e)}")
            return False


# Global instance for easy access
_s3_service = None


def get_s3_service() -> S3UploadService:
    """Get or create S3 service instance."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3UploadService()
    return _s3_service
