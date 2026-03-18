from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.UserView.as_view(), name='users'),
    path('users/<int:pk>/', views.UserView.as_view(), name='users'),
    path('token/', views.CustomAuthToken.as_view(), name='token_auth'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.MeView.as_view(), name='me'),
    path('permissions/', views.PermissionListView.as_view(), name='me'),
    path('change_password/', views.PasswordChangeView.as_view(), name='change_password'),

    path('preferences/', views.UserPreferencesView.as_view(), name='preferences'),
    path('preferences/reset/', views.ResetPreferencesView.as_view(), name='reset-preferences'),
    path('preferences/extra/', views.ExtraSettingView.as_view(), name='extra-settings'),
    path('preferences/extra/<str:key>/', views.ExtraSettingView.as_view(), name='extra-setting-detail'),
    
    path("password-reset/", views.PasswordResetRequestAPIView.as_view(), name="api_password_reset"),
    path("password-reset/confirm/", views.PasswordResetConfirmAPIView.as_view(), name="api_password_reset_confirm"),
]