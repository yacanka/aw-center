"""Chapter order in the manager and end-user editions of the same continuous tour."""
ORDER = """
intro compliance-dashboard login notice attention compliance-register compliance-workflow
compliance-decisions compliance-conflict compliance-archive compliance-import compliance-doors
compliance-numbering compliance-inspection compliance-settings compliance-export compliance-viewer
document-covers document-analysis job-jira-draft jira-watcher jira-assess jira-lists jira-subtasks jira-dcc jira-ecr jira-recovery provider-retry
outlook workflow pilot jobs failure cancel compare excel compare-pdf pdf media gallery galeri-bakim
ddf ddf-detail hub doors scripter eslesme doorsdev nesne poc baglama teamcenter assistant
people panels assignments accounts invites invitation-audit settings member-password public-recovery viewer reset reset-apply closing
""".split()

def position(scene):
    if scene['id'] in ORDER:return ORDER.index(scene['id'])
    if scene['route'].startswith('/app/compdocs'):return ORDER.index('compliance-viewer')-.5
    if scene['route'].startswith('/app/jira'):return ORDER.index('jira-ecr')+.5
    return ORDER.index('closing')-.5
