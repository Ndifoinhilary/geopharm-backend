import os
# apps/user_accounts/validators.py
import re
import threading
from io import BytesIO
import logging

from PIL import Image, ImageOps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
logger = logging.getLogger(__name__)



def validate_password_strength(password):
    """
    Validates that a password meets minimum security requirements:
    - At least 8 characters
    - Contains uppercase letters
    - Contains lowercase letters
    - Contains at least one digit
    - Contains at least one special character
    """
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")

    if not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain at least one uppercase letter.")

    if not re.search(r'[a-z]', password):
        raise ValidationError("Password must contain at least one lowercase letter.")

    if not re.search(r'[0-9]', password):
        raise ValidationError("Password must contain at least one digit.")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError("Password must contain at least one special character.")

    # Check for common patterns
    common_patterns = ['password', '123456', 'qwerty', 'admin']
    if any(pattern in password.lower() for pattern in common_patterns):
        raise ValidationError("Password contains common easily-guessed patterns.")


def generate_otp_code(length=6):
    """
    Generate a random numeric code of a specified length.

    Args:
        length (int): The length of the code to generate. Default is 6.

    Returns:
        str: A random numeric code of the specified length.
    """
    import random
    import string

    return ''.join(random.choice(string.digits) for _ in range(length))


class ImageProcessor:
    """
    Utility class for image processing operations.
    """

    ALLOWED_FORMATS = ['JPEG', 'PNG', 'WEBP']
    MAX_FILE_SIZE = 5 * 1024 * 1024
    THUMBNAIL_SIZES = {
        'small': (50, 50),
        'medium': (150, 150),
        'large': (300, 300),
    }

    @staticmethod
    def validate_image(image_file):
        """
        Validate uploaded image file.
        """
        if image_file.size > ImageProcessor.MAX_FILE_SIZE:
            raise ValidationError(
                _('Image file size cannot exceed %(max_size)s MB.') % {
                    'max_size': ImageProcessor.MAX_FILE_SIZE / (1024 * 1024)
                }
            )

        try:
            img = Image.open(image_file)
            img.verify()
        except Exception:
            raise ValidationError(_('Invalid image file.'))

        image_file.seek(0)
        img = Image.open(image_file)
        if img.format not in ImageProcessor.ALLOWED_FORMATS:
            raise ValidationError(
                _('Unsupported image format. Allowed formats: %(formats)s') % {
                    'formats': ', '.join(ImageProcessor.ALLOWED_FORMATS)
                }
            )

    @staticmethod
    def optimize_image(image_file, max_size=(800, 800), quality=85):
        """
        Optimize image for web use.
        """
        img = Image.open(image_file)

        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background

        img = ImageOps.exif_transpose(img)

        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)

        # Use the original filename or generate a new one, ensuring it has a .jpg extension
        filename = os.path.splitext(image_file.name)[0] + '.jpg'
        return ContentFile(output.read(), name=filename)

    @staticmethod
    def get_image_info(image_file):
        """
        Get image information.
        """
        img = Image.open(image_file)
        return {
            'format': img.format,
            'mode': img.mode,
            'size': img.size,
            'width': img.size[0],
            'height': img.size[1],
        }


def validate_profile_image(image):
    """
    Validator for profile images.
    """
    ImageProcessor.validate_image(image)


def validate_image_aspect_ratio(image, min_ratio=0.5, max_ratio=2.0):
    """
    Validate image aspect ratio.
    """
    img = Image.open(image)
    ratio = img.size[0] / img.size[1]

    if ratio < min_ratio or ratio > max_ratio:
        raise ValidationError(
            _('Image aspect ratio must be between %(min)s and %(max)s.') % {
                'min': min_ratio,
                'max': max_ratio
            }
        )



def validate_certificate_size_format(file_uploaded):
    """
    Validate the uploaded certificate file for size and format (image or PDF).

    :param file_uploaded: Uploaded file object
    :raises ValidationError: If a file is too large or has an unsupported format
    """
    max_file_size = ImageProcessor.MAX_FILE_SIZE
    allowed_formats = ['JPEG', 'PNG', 'WEBP', 'PDF']

    if file_uploaded.size > max_file_size:
        raise ValidationError(
            _('File size cannot exceed %(max_size)s MB.') % {
                'max_size': max_file_size / (1024 * 1024)
            }
        )

    file_ext = os.path.splitext(file_uploaded.name)[1].lower()
    if file_ext == '.pdf':
        return

    try:
        img = Image.open(file_uploaded)
        img.verify()
    except Exception:
        raise ValidationError(_('Invalid image file.'))

    file_uploaded.seek(0)
    img = Image.open(file_uploaded)
    if img.format not in allowed_formats:
        raise ValidationError(
            _('Unsupported file format. Allowed formats: %(formats)s') % {
                'formats': ', '.join(allowed_formats)
            }
        )



def send_email_with_template(data: dict, template_name: str, context: dict, recipient: list):
    def send():
        try:
            email_body = render_to_string(f'emails/{template_name}', context)
            email = EmailMessage(
                subject=data['subject'],
                body=email_body,
                from_email=settings.EMAIL_HOST_USER,
                to=recipient,
            )
            email.content_subtype = 'html'
            email.send()
            logger.info('Email sent')
        except Exception as e:
            print("❌ EMAIL FAILED:", str(e))

    thread = threading.Thread(target=send)
    thread.start()