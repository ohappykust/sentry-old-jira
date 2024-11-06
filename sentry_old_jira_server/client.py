from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from django.urls import reverse
from requests import PreparedRequest

from sentry.identity.services.identity.model import RpcIdentity
from sentry.integrations.client import ApiClient
from sentry.integrations.models.integration import Integration
from sentry.integrations.services.integration.model import RpcIntegration
from sentry.silo.base import control_silo_function
from sentry.utils import jwt
from sentry.utils.http import absolute_uri

logger = logging.getLogger(__name__)

JIRA_KEY = f"{urlparse(absolute_uri()).hostname}.jira"
ISSUE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")
CUSTOMFIELD_PREFIX = "customfield_"


class OldJiraServerClient(ApiClient):
    COMMENTS_URL = "/rest/api/2/issue/%s/comment"
    COMMENT_URL = "/rest/api/2/issue/%s/comment/%s"
    STATUS_URL = "/rest/api/2/status"
    CREATE_URL = "/rest/api/2/issue"
    ISSUE_URL = "/rest/api/2/issue/%s"
    ISSUE_FIELDS_URL = "/rest/api/2/issue/createmeta/%s/issuetypes/%s"
    ISSUE_TYPES_URL = "/rest/api/2/issue/createmeta/%s/issuetypes"
    PRIORITIES_URL = "/rest/api/2/priority"
    PROJECT_URL = "/rest/api/2/project"
    SEARCH_URL = "/rest/api/2/search/"
    VERSIONS_URL = "/rest/api/2/project/%s/versions"
    USERS_URL = "/rest/api/2/user/assignable/search"
    USER_URL = "/rest/api/2/user"
    SERVER_INFO_URL = "/rest/api/2/serverInfo"
    ASSIGN_URL = "/rest/api/2/issue/%s/assignee"
    TRANSITION_URL = "/rest/api/2/issue/%s/transitions"
    AUTOCOMPLETE_URL = "/rest/api/2/jql/autocompletedata/suggestions"
    PROPERTIES_URL = "/rest/api/3/issue/%s/properties/%s"

    integration_name = "old_jira_server"

    # This timeout is completely arbitrary. Jira doesn't give us any
    # caching headers to work with. Ideally we want a duration that
    # lets the user make their second jira issue with cached data.
    cache_time = 240

    def __init__(
            self,
            integration: RpcIntegration | Integration,
            identity: RpcIdentity,
            logging_context: Any | None = None,
    ):
        self.base_url = integration.metadata["base_url"]
        self.identity = identity
        super().__init__(
            integration_id=integration.id,
            verify_ssl=integration.metadata["verify_ssl"],
            logging_context=logging_context,
        )

    def get_cache_prefix(self):
        return "sentry-old-jira-server:"

    def finalize_request(self, prepared_request: PreparedRequest) -> PreparedRequest:
        return self.authorize_request(prepared_request=prepared_request)

    def authorize_request(self, prepared_request: PreparedRequest):
        """Jira Server authorizes with RSA-signed OAuth1 scheme"""
        if not self.identity:
            return prepared_request
        auth_scheme = (
            self.identity.data["username"],
            self.identity.data["password"],
        )
        prepared_request.prepare_auth(auth=auth_scheme)
        return prepared_request

    def user_id_get_param(self):
        return "username"

    def user_id_field(self):
        return "name"

    def user_query_param(self):
        return "username"

    def get_issue(self, issue_id):
        return self.get(self.ISSUE_URL % (issue_id,))

    def search_issues(self, query):
        q = query.replace('"', '\\"')
        # check if it looks like an issue id
        if ISSUE_KEY_RE.match(query):
            jql = f'id="{q}"'
        else:
            jql = f'text ~ "{q}"'
        return self.get(self.SEARCH_URL, params={"jql": jql})

    def create_comment(self, issue_key, comment):
        return self.post(self.COMMENTS_URL % issue_key, data={"body": comment})

    def update_comment(self, issue_key, comment_id, comment):
        return self.put(self.COMMENT_URL % (issue_key, comment_id), data={"body": comment})

    def get_projects_list(self, cached: bool = True):
        if not cached:
            return self.get(self.PROJECT_URL)
        return self.get_cached(self.PROJECT_URL)

    def get_issue_types(self, project_id):
        # Get a list of issue types for the given project
        return self.get_cached(self.ISSUE_TYPES_URL % (project_id))

    def get_issue_fields(self, project_id, issue_type_id):
        # Get a list of fields for the issue type and project
        return self.get_cached(self.ISSUE_FIELDS_URL % (project_id, issue_type_id))

    def get_project_key_for_id(self, project_id) -> str:
        if not project_id:
            return ""
        projects = self.get_projects_list()
        for project in projects:
            if project["id"] == project_id:
                return project["key"]
        return ""

    def get_versions(self, project):
        return self.get_cached(self.VERSIONS_URL % project)

    def get_priorities(self):
        """
        XXX(schew2381): There is an existing bug where we fetch and show all project priorities instead of scoping
        them to the selected project. This is fine when manually creating a Jira Server issue b/c we surface that
        the selected priority is not available. However for the alert rule action, you can save the action with an
        invalid priority for the chosen project. We surface this issue externally in our docs:
        https://docs.sentry.io/product/integrations/issue-tracking/jira/#issue-alert-not-creating-jira-issues

        We are limited by the Jira Server API b/c fetching priorities requires global/project admin permissions.
        There is currently no workaround for this!

        Please DO NOT attempt to use the following APIs:
        https://docs.atlassian.com/software/jira/docs/api/REST/9.11.0/#api/2/priorityschemes-getPrioritySchemes
        https://docs.atlassian.com/software/jira/docs/api/REST/9.11.0/#api/2/project/{projectKeyOrId}/priorityscheme-getAssignedPriorityScheme

        """
        return self.get_cached(self.PRIORITIES_URL)

    def get_users_for_project(self, project):
        # Jira Server wants a project key, while cloud is indifferent.
        project_key = self.get_project_key_for_id(project)
        return self.get_cached(self.USERS_URL, params={"project": project_key})

    def search_users_for_project(self, project, username):
        # Jira Server wants a project key, while cloud is indifferent.
        project_key = self.get_project_key_for_id(project)
        return self.get_cached(
            self.USERS_URL, params={"project": project_key, self.user_query_param(): username}
        )

    def search_users_for_issue(self, issue_key, email):
        return self.get_cached(
            self.USERS_URL, params={"issueKey": issue_key, self.user_query_param(): email}
        )

    def get_user(self, user_id):
        user_id_get_param = self.user_id_get_param()
        return self.get_cached(self.USER_URL, params={user_id_get_param: user_id})

    def create_issue(self, raw_form_data):
        data = {"fields": raw_form_data}
        return self.post(self.CREATE_URL, data=data)

    def get_server_info(self):
        return self.get(self.SERVER_INFO_URL)

    def get_valid_statuses(self):
        return self.get_cached(self.STATUS_URL)

    def get_transitions(self, issue_key):
        return self.get_cached(self.TRANSITION_URL % issue_key)["transitions"]

    def transition_issue(self, issue_key, transition_id):
        return self.post(
            self.TRANSITION_URL % issue_key, data={"transition": {"id": transition_id}}
        )

    def assign_issue(self, key, name_or_account_id):
        user_id_field = self.user_id_field()
        return self.put(self.ASSIGN_URL % key, data={user_id_field: name_or_account_id})

    def set_issue_property(self, issue_key, badge_num):
        module_key = "sentry-issues-glance"
        properties_key = f"com.atlassian.jira.issue:{JIRA_KEY}:{module_key}:status"
        data = {"type": "badge", "value": {"label": badge_num}}
        return self.put(self.PROPERTIES_URL % (issue_key, properties_key), data=data)

    def get_field_autocomplete(self, name, value):
        if name.startswith(CUSTOMFIELD_PREFIX):
            # Transform `customfield_0123` into `cf[0123]`
            cf_id = name[len(CUSTOMFIELD_PREFIX):]
            jql_name = f"cf[{cf_id}]"
        else:
            jql_name = name
        return self.get_cached(
            self.AUTOCOMPLETE_URL, params={"fieldName": jql_name, "fieldValue": value}
        )


class OldJiraServerSetupClient(ApiClient):
    """
    Client for making requests to JiraServer for setup.
    """

    @control_silo_function
    def __init__(self, base_url, username, password, verify_ssl=True):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

    def create_issue_webhook(self, external_id, secret):
        auth = (self.username, self.password)
        # Create a JWT token that we can add to the webhook URL
        # so we can locate the matching integration later.
        token = jwt.encode({"id": external_id}, secret)
        path = reverse("sentry-extensions-oldjiraserver-issue-updated", kwargs={"token": token})
        data = {
            "name": "Sentry Issue Sync",
            "url": absolute_uri(path),
            "events": ["jira:issue_created", "jira:issue_updated"],
        }
        return self.post("/rest/webhooks/1.0/webhook", auth=auth, data=data)
