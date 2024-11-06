from django.urls import re_path

from .search import OldJiraServerSearchEndpoint
from .webhooks import OldJiraServerIssueUpdatedWebhook

# If updating/adding URLs here, make sure to update the JiraServerRequestParser as well
urlpatterns = [
    re_path(
        r"^issue-updated/(?P<token>[^\/]+)/$",
        OldJiraServerIssueUpdatedWebhook.as_view(),
        name="sentry-extensions-oldjiraserver-issue-updated",
    ),
    re_path(
        r"^search/(?P<organization_id_or_slug>[^\/]+)/(?P<integration_id>\d+)/$",
        OldJiraServerSearchEndpoint.as_view(),
        name="sentry-extensions-oldjiraserver-search",
    ),
]
