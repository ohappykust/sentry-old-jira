# Sentry Old Jira Server Integration

![Sentry Old Jira Server Integration](assets/logo.png)


<p align="center">
  <a href="https://github.com/ohappykust/sentry-old-jira-server">Original repository</a>
|
<a href="https://pypi.org/project/sentry-old-jira-server">Original releases</a>
</p>

## Overview

The **Sentry Old Jira Server Integration** is a fork of the official Jira integration, designed to allow you to use this powerful integration from Sentry team with old Jira versions by allowing setup integration with username and password.

You can read more about Sentry Jira Integration [on official Sentry Documentation](https://docs.sentry.io/organization/integrations/issue-tracking/jira/).

## New Features

- **Support Basic Authentication**: Use Jira username and password for authentication.

## Installation

To install the Sentry Old Jira Integration add it to your ```sentry/enhance_image.sh``` file:

```bash
pip install sentry-old-jira-server
```

And enable it in ```sentry.conf.py```:

```python
SENTRY_DEFAULT_INTEGRATIONS = (
    *SENTRY_DEFAULT_INTEGRATIONS,
    "sentry_old_jira_server.integration.OldJiraServerIntegrationProvider"
)
```
Then run ```install.sh``` script to reconfgure your Sentry installation. All done!