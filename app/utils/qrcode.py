import qrcode
import io
import base64
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.student import get_student_by_id
from app.core.exceptions import NotFoundException, InvalidDataException


async def generate_student_qr_code(student_id: int, db: AsyncSession):
    """Generate QR code for a student"""
    try:
        student = await get_student_by_id(db, student_id)
    except NotFoundException:
        return None
    
    # Create QR code data
    qr_data = f"STUDENT:{student.id}:{student.student_id}:{student.school_id}"
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


async def verify_student_qr_code(qr_data: str, db: AsyncSession):
    """Verify student QR code data"""
    try:
        parts = qr_data.split(":")
        if len(parts) != 4 or parts[0] != "STUDENT":
            raise InvalidDataException("Invalid QR code format.")
        
        student_id = int(parts[1])
        student_code = parts[2]
        school_id = int(parts[3])
        
        student = await get_student_by_id(db, student_id)
        if student.student_id != student_code or student.school_id != school_id:
            raise InvalidDataException("Invalid QR code data.")
        
        return student
    except (ValueError, IndexError):
        raise InvalidDataException("Invalid QR code data.")
    except NotFoundException:
        raise InvalidDataException("Student not found for the provided QR code.")