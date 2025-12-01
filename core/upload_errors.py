"""
Upload Error Code System
Standardized error codes for client upload processing
"""

# Error Code Categories
UPLOAD_ERROR_CODES = {
    # File-related errors (001-019)
    'UPLOAD_001': {
        'message': 'File format not supported. Only CSV, XLSX, and XLS files are allowed.',
        'category': 'file_format',
        'user_action': 'Please upload a CSV, XLSX, or XLS file.'
    },
    'UPLOAD_002': {
        'message': 'File is empty or contains no data.',
        'category': 'file_content',
        'user_action': 'Please ensure your file contains data rows.'
    },
    'UPLOAD_003': {
        'message': 'File has no columns or invalid structure.',
        'category': 'file_structure',
        'user_action': 'Please check your file format and ensure it has column headers.'
    },
    'UPLOAD_004': {
        'message': 'File encoding could not be determined.',
        'category': 'file_encoding',
        'user_action': 'Please save your file as UTF-8 encoded CSV and try again.'
    },
    'UPLOAD_005': {
        'message': 'File is too large for synchronous processing.',
        'category': 'file_size',
        'user_action': 'Please split your file into smaller chunks (recommended: <10,000 rows per file).'
    },
    
    # Validation errors (020-039)
    'UPLOAD_020': {
        'message': 'Missing required columns.',
        'category': 'validation',
        'user_action': 'Please ensure your file includes all required columns.'
    },
    'UPLOAD_021': {
        'message': 'Invalid data format in row.',
        'category': 'validation',
        'user_action': 'Please check the data format in the specified row.'
    },
    'UPLOAD_022': {
        'message': 'Invalid date format.',
        'category': 'validation',
        'user_action': 'Please use YYYY-MM-DD format for dates.'
    },
    'UPLOAD_023': {
        'message': 'Invalid email format.',
        'category': 'validation',
        'user_action': 'Please check email addresses in your file.'
    },
    'UPLOAD_024': {
        'message': 'Invalid phone number format.',
        'category': 'validation',
        'user_action': 'Please check phone numbers in your file.'
    },
    
    # Database errors (040-059)
    'UPLOAD_040': {
        'message': 'Database connection timeout.',
        'category': 'database',
        'user_action': 'The upload is taking too long. Please try a smaller file or contact support.'
    },
    'UPLOAD_041': {
        'message': 'Database connection lost.',
        'category': 'database',
        'user_action': 'Database connection was lost. Please try again.'
    },
    'UPLOAD_042': {
        'message': 'Database transaction failed.',
        'category': 'database',
        'user_action': 'Database operation failed. Please try again or contact support.'
    },
    'UPLOAD_043': {
        'message': 'Bulk operation failed.',
        'category': 'database',
        'user_action': 'Failed to save records. Please check your data and try again.'
    },
    
    # Processing errors (060-079)
    'UPLOAD_060': {
        'message': 'Web server timeout.',
        'category': 'timeout',
        'user_action': 'Upload timed out. Please try a smaller file or contact support for large file processing.'
    },
    'UPLOAD_061': {
        'message': 'Memory limit exceeded.',
        'category': 'resource',
        'user_action': 'File is too large. Please split into smaller files.'
    },
    'UPLOAD_062': {
        'message': 'Processing timeout.',
        'category': 'timeout',
        'user_action': 'Upload is taking too long. Please try a smaller file.'
    },
    
    # Business logic errors (080-099)
    'UPLOAD_080': {
        'message': 'Program not found.',
        'category': 'business_logic',
        'user_action': 'Please ensure the program exists in the system before uploading.'
    },
    'UPLOAD_081': {
        'message': 'Department not found.',
        'category': 'business_logic',
        'user_action': 'Please ensure the department exists in the system.'
    },
    'UPLOAD_082': {
        'message': 'Duplicate client detected.',
        'category': 'business_logic',
        'user_action': 'A client with this information already exists. Review duplicate flags.'
    },
    'UPLOAD_083': {
        'message': 'Client ID already exists with different source.',
        'category': 'business_logic',
        'user_action': 'This client ID is already associated with a different source system.'
    },
    
    # System errors (100-119)
    'UPLOAD_100': {
        'message': 'Unexpected error occurred.',
        'category': 'system',
        'user_action': 'An unexpected error occurred. Please contact support with the error code.'
    },
    'UPLOAD_101': {
        'message': 'Permission denied.',
        'category': 'permission',
        'user_action': 'You do not have permission to upload clients. Contact your administrator.'
    },
    'UPLOAD_102': {
        'message': 'Upload log creation failed.',
        'category': 'system',
        'user_action': 'Failed to create upload log. Please try again.'
    },
}


class UploadError(Exception):
    """Custom exception for upload errors with error codes"""
    
    def __init__(self, code, message=None, details=None, row_number=None, raw_error=None):
        self.code = code
        self.message = message or UPLOAD_ERROR_CODES.get(code, {}).get('message', 'Unknown error')
        self.details = details or {}
        self.row_number = row_number
        self.raw_error = raw_error
        self.category = UPLOAD_ERROR_CODES.get(code, {}).get('category', 'unknown')
        self.user_action = UPLOAD_ERROR_CODES.get(code, {}).get('user_action', 'Please try again.')
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert error to dictionary for JSON response"""
        return {
            'code': self.code,
            'message': self.message,
            'category': self.category,
            'user_action': self.user_action,
            'details': self.details,
            'row_number': self.row_number,
            'raw_error': str(self.raw_error) if self.raw_error else None
        }
    
    def to_log_dict(self):
        """Convert error to dictionary for logging"""
        return {
            'error_code': self.code,
            'error_message': self.message,
            'error_category': self.category,
            'row_number': self.row_number,
            'details': self.details,
            'raw_error': str(self.raw_error) if self.raw_error else None,
            'traceback': self.details.get('traceback') if isinstance(self.details, dict) else None
        }


def get_error_code_for_exception(exception):
    """Map Python exceptions to error codes"""
    error_str = str(exception).lower()
    exception_type = type(exception).__name__
    
    # Database errors
    if 'timeout' in error_str or 'timed out' in error_str:
        if 'database' in error_str or 'connection' in error_str:
            return 'UPLOAD_040'
        return 'UPLOAD_060'
    
    if 'connection' in error_str and ('lost' in error_str or 'closed' in error_str):
        return 'UPLOAD_041'
    
    if 'memory' in error_str or 'out of memory' in error_str:
        return 'UPLOAD_061'
    
    if 'permission' in error_str or 'access' in error_str:
        return 'UPLOAD_101'
    
    if 'validation' in error_str or 'invalid' in error_str:
        return 'UPLOAD_021'
    
    # Exception type mapping
    if exception_type in ['TimeoutError', 'socket.timeout']:
        return 'UPLOAD_060'
    
    if exception_type in ['MemoryError']:
        return 'UPLOAD_061'
    
    if exception_type in ['IntegrityError', 'DatabaseError']:
        return 'UPLOAD_042'
    
    # Default
    return 'UPLOAD_100'

