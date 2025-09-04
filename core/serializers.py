from rest_framework import serializers
from .models import User, Staff, Role, Department, Program


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'external_id', 'email', 'username', 'first_name', 'last_name', 'is_active', 'created_at']
        read_only_fields = ['id', 'external_id', 'created_at']


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['external_id', 'name', 'owner']


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['external_id', 'name', 'description', 'permissions']


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    roles = RoleSerializer(many=True, read_only=True)
    
    class Meta:
        model = Staff
        fields = ['external_id', 'user', 'roles']
        read_only_fields = ['external_id']


class ProgramSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    
    class Meta:
        model = Program
        fields = ['external_id', 'name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
        read_only_fields = ['external_id']
