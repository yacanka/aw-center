from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework import serializers

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User, Permission, update_last_login
from django.shortcuts import get_object_or_404 
from django.http import HttpResponse

from .models import UserPreferences
from .serializers import UserSerializer, PermissionSerializer, PasswordChangeSerializer, UserPreferencesSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer
from .permissions import UserPermission


@permission_classes([AllowAny])
class UserView(APIView):
    def get(self, request, pk=None):
        if pk:
            user = get_object_or_404(User, pk=pk)
            serializer = UserSerializer(user)
            return Response(serializer.data)
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserSerializer(user, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.delete()
        return Response("User deleted.", status=status.HTTP_204_NO_CONTENT)

@permission_classes([AllowAny])
class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        update_last_login(None, user)
        print(f"{user} logged in.")
        return response

@permission_classes([IsAuthenticated])
class LogoutView(APIView):
    def post(self, request):
        request.user.auth_token.delete()
        return Response("Logout successful.", status=status.HTTP_200_OK)

@permission_classes([IsAuthenticated])
class MeView(APIView):
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)

class PasswordChangeView(APIView):
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            
            update_session_auth_hash(request, user)
        
            return Response({"message": "Password is updated successfully."}, status=200)
        
        return Response(serializer.errors, status=400)


class PermissionListView(APIView):
    permission_classes = [UserPermission]

    def get(self, request):
        permissions = Permission.objects.all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        serializer = UserPreferencesSerializer(request.user.preferences)
        return Response(serializer.data)
    
    def put(self, request):
        serializer = UserPreferencesSerializer(
            request.user.preferences,
            data=request.data
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        serializer = UserPreferencesSerializer(
            request.user.preferences,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPreferencesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        request.user.preferences.reset_to_defaults()
        serializer = UserPreferencesSerializer(request.user.preferences)
        return Response({
            'message': 'Preferences reset to defaults',
            'preferences': serializer.data
        })

class ExtraSettingView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, key):
        value = request.user.preferences.get_extra_setting(key)
        if value is None:
            return Response(
                {'error': f"Setting '{key}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response({key: value})
    
    def post(self, request):
        key = request.data.get('key')
        value = request.data.get('value')
        
        if not key:
            return Response(
                {'error': 'Key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        request.user.preferences.set_extra_setting(key, value)
        return Response({
            'message': 'Setting saved successfully',
            key: value
        })
    
    def delete(self, request, key):
        preferences = request.user.preferences
        if key in preferences.extra_settings:
            del preferences.extra_settings[key]
            preferences.save(update_fields=['extra_settings', 'updated_at'])
            return Response({'message': f"Setting '{key}' deleted"})
        return Response(
            {'error': f"Setting '{key}' not found"},
            status=status.HTTP_404_NOT_FOUND
        )

class PasswordResetRequestAPIView(APIView):
    permission_classes = []  # AllowAny

    def post(self, request):
        ser = PasswordResetRequestSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "If the email is registered, a link has been sent."}, status=status.HTTP_200_OK)

class PasswordResetConfirmAPIView(APIView):
    permission_classes = []  # AllowAny

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
