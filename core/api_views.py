from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
import logging
from .models import User, Staff, Role, Department
from .serializers import UserSerializer, StaffSerializer

# Set up logging
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    logger.info(f"Registration attempt started. Data: {request.data}")
    
    try:
        data = request.data
        logger.info(f"Received registration data: {data}")
        
        # Validate required fields
        required_fields = ['email', 'username', 'first_name', 'last_name', 'password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.warning(f"Registration failed - {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if email already exists
        if User.objects.filter(email=data.get('email')).exists():
            error_msg = 'User with this email already exists'
            logger.warning(f"Registration failed - {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if username already exists
        if User.objects.filter(username=data.get('username')).exists():
            error_msg = 'User with this username already exists'
            logger.warning(f"Registration failed - {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate password
        password = data.get('password')
        try:
            validate_password(password)
            logger.info("Password validation passed")
        except ValidationError as e:
            error_msg = f"Password validation failed: {e.messages}"
            logger.warning(f"Registration failed - {error_msg}")
            return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create user and staff in a transaction
        with transaction.atomic():
            logger.info("Creating user...")
            user = User.objects.create_user(
                email=data.get('email'),
                username=data.get('username'),
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                password=password
            )
            logger.info(f"User created successfully: {user.id}")
            
            logger.info("Creating staff profile...")
            staff = Staff.objects.create(
                user=user
            )
            logger.info(f"Staff profile created successfully: {staff.id}")
            
            # Assign default role
            default_role = Role.objects.filter(name='User').first()
            if default_role:
                staff.staffrole_set.create(role=default_role)
                logger.info(f"Assigned default role 'User' to staff: {staff.id}")
            else:
                logger.warning("No default 'User' role found!")
        
        # Generate tokens
        logger.info("Generating JWT tokens...")
        refresh = RefreshToken.for_user(user)
        
        response_data = {
            'user': UserSerializer(user).data,
            'staff': StaffSerializer(staff).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }
        
        logger.info(f"Registration successful for user: {user.email}")
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        error_msg = f"Unexpected error during registration: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return Response({'error': 'Registration failed. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    logger.info(f"Login attempt started. Data: {request.data}")
    
    try:
        data = request.data
        email = data.get('email')
        password = data.get('password')
        
        logger.info(f"Login attempt for email: {email}")
        
        if not email or not password:
            error_msg = 'Email and password are required'
            logger.warning(f"Login failed - {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info("Authenticating user...")
        user = authenticate(username=email, password=password)
        
        if user is None:
            error_msg = 'Invalid credentials'
            logger.warning(f"Login failed - {error_msg} for email: {email}")
            return Response({'error': error_msg}, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_active:
            error_msg = 'Account is disabled'
            logger.warning(f"Login failed - {error_msg} for email: {email}")
            return Response({'error': error_msg}, status=status.HTTP_401_UNAUTHORIZED)
        
        logger.info(f"User authenticated successfully: {user.id}")
        
        try:
            staff = user.staff_profile
            logger.info(f"Staff profile found: {staff.id}")
        except Staff.DoesNotExist:
            error_msg = 'Staff profile not found'
            logger.error(f"Login failed - {error_msg} for user: {user.id}")
            return Response({'error': error_msg}, status=status.HTTP_401_UNAUTHORIZED)
        
        logger.info("Generating JWT tokens...")
        refresh = RefreshToken.for_user(user)
        
        response_data = {
            'user': UserSerializer(user).data,
            'staff': StaffSerializer(staff).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }
        
        logger.info(f"Login successful for user: {user.email}")
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_msg = f"Unexpected error during login: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return Response({'error': 'Login failed. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        token = RefreshToken(refresh_token)
        access_token = str(token.access_token)
        
        return Response({
            'access': access_token
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def logout(request):
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def user_profile(request):
    try:
        user = request.user
        staff = user.staff_profile
        
        return Response({
            'user': UserSerializer(user).data,
            'staff': StaffSerializer(staff).data,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def debug_info(request):
    """Debug endpoint to check system status"""
    try:
        roles_count = Role.objects.count()
        departments_count = Department.objects.count()
        users_count = User.objects.count()
        staff_count = Staff.objects.count()
        
        roles = list(Role.objects.values('name', 'description'))
        departments = list(Department.objects.values('name', 'owner'))
        
        return Response({
            'status': 'ok',
            'counts': {
                'roles': roles_count,
                'departments': departments_count,
                'users': users_count,
                'staff': staff_count,
            },
            'roles': roles,
            'departments': departments,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Debug info error: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
