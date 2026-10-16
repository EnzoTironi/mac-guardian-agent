"""Grant the owner's one-time consents the way the agent must: preview, then yes."""

# These suites were written for the whole home folder; the default is Downloads and Desktop.
HOME_TREE = ("Downloads", "Desktop", ".")


def grant_all(guardian, roots=HOME_TREE):
    for name in roots:
        if name != ".":
            (guardian.home / name).mkdir(parents=True, exist_ok=True)
    guardian.configure_organization(list(roots))
    guardian.organize(False)
    guardian.grant_consent("organize", "Test owner: yes, organize those files")
    guardian.care_for_projects(False, record=True)
    # The preview walks projects; a later test creates its own, so start fresh.
    guardian.__dict__.pop("_project_cache", None)
    guardian.grant_consent("github-projects", "Test owner: yes, back up my code privately")
