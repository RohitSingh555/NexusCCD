# Central Client Database - User Flow Documentation

## Authentication System Overview

The CCD system implements a comprehensive JWT-based authentication system with role-based access control. Here's how different user types interact with the system:

## User Roles & Permissions

### 1. **Admin Role**
- **Full system access**
- Can manage all users, clients, programs, and staff
- Can approve/reject pending changes
- Access to all reports and analytics
- Can modify system settings

### 2. **Manager Role**
- **Department management access**
- Can view all data within their department
- Can approve changes for their department
- Can manage staff within their department
- Access to department-specific reports

### 3. **Staff Role**
- **Basic operational access**
- Can view and edit client information
- Can view programs and enrollments
- Can create client notes and documents
- Limited reporting access

### 4. **Viewer Role**
- **Read-only access**
- Can view client and program information
- Cannot make any modifications
- Access to basic reports only

## User Flow Scenarios

### **Scenario 1: New User Registration**

1. **Landing Page**: User visits the homepage
2. **Sign Up**: Clicks "Sign Up" button in navigation
3. **Registration Modal**: Fills out registration form with:
   - First Name, Last Name
   - Username (unique)
   - Email (unique)
   - Phone Number (optional)
   - Password & Confirmation
4. **Account Creation**: System creates user account and staff profile
5. **Default Role Assignment**: User is assigned "Staff" role by default
6. **Auto-Login**: User is automatically logged in after successful registration
7. **Dashboard Access**: User sees personalized navigation based on their role

### **Scenario 2: Existing User Login**

1. **Landing Page**: User visits the homepage
2. **Sign In**: Clicks "Login" button in navigation
3. **Login Modal**: Enters email and password
4. **Authentication**: System validates credentials via JWT
5. **Role-Based Navigation**: User sees navigation options based on their role
6. **Dashboard Access**: User is redirected to appropriate dashboard

### **Scenario 3: Role-Based Navigation**

#### **For Authenticated Users:**
- **Navigation Items**: Home, Clients, Programs, Staff, Reports
- **User Dropdown**: Profile, Settings, Sign Out
- **Mobile Menu**: Same options in collapsible mobile menu

#### **For Guest Users:**
- **Navigation Items**: Home only
- **Action Buttons**: Login, Sign Up
- **Mobile Menu**: Login and Sign Up options

### **Scenario 4: Loading States & UX**

1. **Page Load**: Global loading overlay during authentication checks
2. **Form Submission**: Loading spinners on login/register buttons
3. **API Calls**: Loading states for all data fetching operations
4. **Navigation**: Smooth transitions between pages
5. **Notifications**: Success/error messages for user actions

## Technical Implementation

### **Frontend (Alpine.js)**
- **State Management**: Global authentication state
- **JWT Storage**: Access and refresh tokens in localStorage
- **API Integration**: RESTful API calls to Django backend
- **Responsive Design**: Mobile-first approach with TailwindCSS

### **Backend (Django + DRF)**
- **Custom User Model**: Extended AbstractUser with additional fields
- **JWT Authentication**: Simple JWT for token-based auth
- **Role System**: Flexible role-based permissions
- **API Endpoints**: RESTful endpoints for auth operations

### **Security Features**
- **Password Validation**: Django's built-in password validators
- **Token Rotation**: Refresh tokens are rotated on use
- **CORS Configuration**: Proper cross-origin resource sharing
- **Input Validation**: Server-side validation for all inputs

## API Endpoints

### **Authentication Endpoints**
- `POST /core/api/auth/register/` - User registration
- `POST /core/api/auth/login/` - User login
- `POST /core/api/auth/refresh/` - Token refresh
- `POST /core/api/auth/logout/` - User logout
- `GET /core/api/auth/profile/` - User profile

### **Response Format**
```json
{
  "user": {
    "id": 1,
    "external_id": "uuid",
    "email": "user@example.com",
    "username": "username",
    "first_name": "John",
    "last_name": "Doe",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  },
  "staff": {
    "external_id": "uuid",
    "phone_number": "+1234567890",
    "department": {
      "external_id": "uuid",
      "name": "Social Services"
    },
    "roles": [
      {
        "external_id": "uuid",
        "name": "Staff",
        "permissions": ["view_clients", "edit_clients"]
      }
    ]
  },
  "tokens": {
    "access": "jwt_access_token",
    "refresh": "jwt_refresh_token"
  }
}
```

## Error Handling

### **Client-Side Errors**
- Form validation errors
- Network connectivity issues
- Authentication failures
- User-friendly error messages

### **Server-Side Errors**
- Validation errors (400)
- Authentication errors (401)
- Permission errors (403)
- Not found errors (404)
- Server errors (500)

## Future Enhancements

1. **Two-Factor Authentication**: SMS/Email verification
2. **Password Reset**: Email-based password recovery
3. **Remember Me**: Extended session management
4. **Social Login**: Google/Microsoft OAuth integration
5. **Advanced Permissions**: Granular permission system
6. **Audit Logging**: User action tracking
7. **Session Management**: Active session monitoring

## Testing the System

1. **Start the server**: `python manage.py runserver`
2. **Visit homepage**: http://localhost:8000
3. **Test registration**: Click "Sign Up" and create a new account
4. **Test login**: Use existing credentials to log in
5. **Test navigation**: Verify role-based navigation works
6. **Test logout**: Ensure proper session cleanup

The authentication system is now fully functional with beautiful modals, role-based navigation, loading states, and a comprehensive user flow that provides an excellent user experience for all user types.
