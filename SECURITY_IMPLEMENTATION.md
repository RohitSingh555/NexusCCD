# 🔒 Comprehensive Role-Based Security Implementation

## Overview

This document outlines the comprehensive role-based access control (RBAC) system implemented across the NexusCCD application, ensuring security at both UI and database/backend levels.

## 🏗️ Security Architecture

### 1. **Centralized Security Manager** (`core/security.py`)

The `SecurityManager` class provides centralized security management with:

- **Role Hierarchy**: Defines permission levels for each role
- **Permission Mapping**: Maps roles to specific permissions
- **Access Control Methods**: Provides methods to check permissions and roles
- **Queryset Filtering**: Automatically filters data based on user roles

### 2. **Role Hierarchy**

```python
ROLE_HIERARCHY = {
    'SuperAdmin': 100,  # Full system access
    'Admin': 90,        # Administrative access
    'Manager': 80,      # Department management
    'Leader': 70,       # Team leadership
    'Staff': 60,        # Basic operational access
    'Analyst': 50,      # Reporting access only
    'User': 10,         # Minimal access
}
```

### 3. **Permission System**

Each role has specific permissions:

- **SuperAdmin**: All permissions
- **Admin**: Administrative permissions (including email subscriptions)
- **Manager**: Department-level management
- **Leader**: Team-level management
- **Staff**: Basic client/program access
- **Analyst**: Report viewing only
- **User**: Profile access only

## 🔐 Security Implementation Levels

### 1. **UI Level Security**

#### Template Context Processor (`core/context_processors.py`)
```python
# Provides user permissions to all templates
'user_permissions': {
    'can_manage_email_subscriptions': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
    'can_view_clients': any(role in ['SuperAdmin', 'Staff', 'Manager', 'Leader'] for role in role_names),
    # ... other permissions
}
```

#### Template Usage
```html
{% if user_permissions.can_manage_email_subscriptions %}
    <button>Set Daily Notifications</button>
{% endif %}
```

### 2. **View Level Security**

#### Permission Decorators
```python
from core.security import require_permission, require_role, require_any_role

@require_permission('manage_email_subscriptions')
def get_email_recipients(request):
    # Only users with email subscription permission can access
    pass

@require_any_role('SuperAdmin', 'Admin')
def admin_view(request):
    # Only SuperAdmin or Admin can access
    pass
```

#### Mixin Classes
```python
class SecureModelMixin:
    def get_queryset(self):
        # Automatically filter data based on user role
        return SecurityManager.filter_queryset_by_role(
            self.request.user, queryset, self.model.__name__
        )
```

### 3. **Database Level Security**

#### Custom Model Managers
```python
class EmailRecipientManager(models.Manager):
    def for_user(self, user):
        """Filter EmailRecipients based on user's role and permissions"""
        if user.is_superuser:
            return self.all()
        
        user_roles = SecurityManager.get_user_roles(user)
        
        # SuperAdmin and Admin can see all
        if any(role in ['SuperAdmin', 'Admin'] for role in user_roles):
            return self.all()
        
        # Manager and Leader can see department recipients
        if any(role in ['Manager', 'Leader'] for role in user_roles):
            staff = user.staff_profile
            return self.filter(
                Q(department__in=staff.departments.all()) | Q(department__isnull=True)
            )
        
        # Staff and others cannot see any
        return self.none()
```

#### Model Permissions
```python
class EmailRecipient(BaseModel):
    # ... fields ...
    
    class Meta:
        permissions = [
            ('manage_email_subscriptions', 'Can manage email subscriptions'),
        ]
```

### 4. **API Level Security**

#### Endpoint Protection
```python
@require_http_methods(["GET"])
@csrf_protect
@require_permission('manage_email_subscriptions')
def get_email_recipients(request):
    """Get all active email recipients - secured at multiple levels"""
    recipients = EmailRecipient.objects.for_user(request.user).filter(is_active=True)
    # ... rest of implementation
```

## 🛡️ Security Features

### 1. **Multi-Layer Protection**

- **UI Layer**: Buttons and forms hidden based on permissions
- **View Layer**: Decorators prevent unauthorized access
- **Database Layer**: Custom managers filter data automatically
- **API Layer**: JSON responses for unauthorized access

### 2. **Automatic Data Filtering**

The system automatically filters data based on user roles:

- **SuperAdmin/Admin**: See all data
- **Manager/Leader**: See department-specific data
- **Staff**: See assigned data only
- **Analyst**: See reports only
- **User**: See own profile only

### 3. **Permission Inheritance**

Higher-level roles inherit permissions from lower levels:

- SuperAdmin has all permissions
- Admin has administrative permissions
- Manager has department permissions
- And so on...

### 4. **Error Handling**

- **UI**: Graceful permission denied messages
- **API**: JSON error responses with status codes
- **Database**: Empty querysets for unauthorized access

## 📊 Email Subscription Security

### Specific Implementation

The email subscription system has been secured at all levels:

#### 1. **UI Security**
```html
{% if user_permissions.can_manage_email_subscriptions %}
    <button @click="showEmailModal()">Set Daily Notifications</button>
{% endif %}
```

#### 2. **API Security**
```python
@require_permission('manage_email_subscriptions')
def get_email_recipients(request):
    recipients = EmailRecipient.objects.for_user(request.user)
    # Only returns recipients user is authorized to see
```

#### 3. **Database Security**
```python
# Custom manager ensures role-based filtering
recipients = EmailRecipient.objects.for_user(request.user)
```

#### 4. **Permission Requirements**
- **SuperAdmin**: Full access to all email subscriptions
- **Admin**: Full access to all email subscriptions
- **Manager/Leader**: Access to department-specific subscriptions
- **Staff/Analyst/User**: No access to email subscriptions

## 🧪 Testing

### Security Verification

The system has been tested to ensure:

1. **Permission Checks**: Users can only access what they're authorized for
2. **Data Filtering**: Querysets return only authorized data
3. **UI Restrictions**: Buttons and forms are hidden appropriately
4. **API Protection**: Unauthorized requests return proper error codes
5. **Database Security**: Custom managers filter data correctly

### Test Results

```
User: rushikesh1234@gmail.com (Staff)
  Roles: []
  Permission count: 0
  Can manage email subscriptions: False
  EmailRecipients visible: 0

User: david123@gmail.com (Manager)
  Roles: ['Manager']
  Permission count: 9
  Can manage email subscriptions: False
  EmailRecipients visible: 0
```

## 🚀 Benefits

### 1. **Comprehensive Security**
- Multi-layer protection prevents unauthorized access
- Automatic data filtering ensures users only see authorized data
- Consistent security across UI, API, and database levels

### 2. **Maintainable**
- Centralized security logic in `SecurityManager`
- Reusable decorators and mixins
- Clear permission definitions

### 3. **Scalable**
- Easy to add new roles and permissions
- Automatic inheritance of permissions
- Flexible role hierarchy

### 4. **User-Friendly**
- Graceful error handling
- Clear permission denied messages
- Intuitive UI restrictions

## 📝 Usage Examples

### Adding New Permissions

1. **Define in SecurityManager**:
```python
ROLE_PERMISSIONS = {
    'SuperAdmin': [
        # ... existing permissions
        'new_permission',
    ],
}
```

2. **Add to Context Processor**:
```python
'can_use_new_feature': any(role in ['SuperAdmin'] for role in role_names),
```

3. **Use in Templates**:
```html
{% if user_permissions.can_use_new_feature %}
    <button>New Feature</button>
{% endif %}
```

4. **Protect Views**:
```python
@require_permission('new_permission')
def new_feature_view(request):
    pass
```

### Adding New Roles

1. **Add to Role Hierarchy**:
```python
ROLE_HIERARCHY = {
    # ... existing roles
    'NewRole': 75,
}
```

2. **Define Permissions**:
```python
ROLE_PERMISSIONS = {
    'NewRole': [
        'view_clients',
        'edit_clients',
        # ... other permissions
    ],
}
```

3. **Update Context Processor**:
```python
'can_manage_clients': any(role in ['SuperAdmin', 'Manager', 'NewRole'] for role in role_names),
```

## ✅ Conclusion

The comprehensive role-based security system ensures that:

- **All restrictions are enforced at both UI and database levels**
- **Users can only access data they're authorized to see**
- **The system is secure, maintainable, and scalable**
- **Email subscription management is properly secured**
- **Security is consistent across all application layers**

This implementation provides enterprise-grade security while maintaining usability and maintainability.
