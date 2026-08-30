from django.urls import path

from . import views
from .invitation_views import (
    InvitationAcceptView,
    InvitationCollectionView,
    InvitationDetailView,
    InvitationInspectView,
)


urlpatterns = [
    path("", views.UserView.as_view(), name="users"),
    path("<int:pk>/", views.UserView.as_view(), name="user-detail"),
    path("permissions/", views.PermissionListView.as_view(), name="permissions"),
    path("groups/", views.GroupView.as_view(), name="groups"),
    path("groups/<int:pk>/", views.GroupView.as_view(), name="group-detail"),
    path("password/", views.PasswordChangeView.as_view(), name="change-password"),
    path("preferences/", views.UserPreferencesView.as_view(), name="preferences"),
    path("preferences/reset/", views.ResetPreferencesView.as_view(), name="reset-preferences"),
    path("preferences/extra/", views.ExtraSettingView.as_view(), name="extra-settings"),
    path("preferences/extra/<str:key>/", views.ExtraSettingView.as_view(), name="extra-setting-detail"),
    path("password-reset/", views.PasswordResetRequestAPIView.as_view(), name="password-reset"),
    path("password-reset/confirm/", views.PasswordResetConfirmAPIView.as_view(), name="password-reset-confirm"),
    path("invitations/", InvitationCollectionView.as_view(), name="invitation-collection"),
    path("invitations/<int:invitation_id>/", InvitationDetailView.as_view(), name="invitation-detail"),
    path("invitations/inspect/", InvitationInspectView.as_view(), name="invitation-inspect"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
]
