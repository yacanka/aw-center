from enum import Enum

class Projects(Enum):
    HYS = ("HYS", "HYS", "dcc_hys_template.docx", "mail_jira_hys_template.html")
    OZGUR = ("Özgür", "OZG", "dcc_ozg_template.docx", "mail_jira_ozg_template.html")
    GOKBEY = ("Gökbey Jandarma", "GJ", "dcc_gj_template.docx", "mail_jira_gj_template.html")
    
    @property
    def jira_component(self):
        return self.value[0]
    
    @property
    def dcc_label(self):
        return self.value[1]
    
    @property
    def dcc_template_name(self):
        return self.value[2]
    
    @property
    def mail_jira_template_name(self):
        return self.value[3]
    
    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))
    
    @classmethod
    def from_jira_component(cls, value):
        for c in cls:
            if c.jira_component == value:
                return c
        raise ValueError(f"{value} not an available value in supported {cls.__name__}.")
    
    @classmethod
    def from_dcc_label(cls, value):
        for c in cls:
            if c.dcc_label == value:
                return c
        raise ValueError(f"{value} not an available value in supported {cls.__name__}.")
    
    @classmethod
    def has_jira_component(cls, jira_component: str) -> bool:
        return any(item.jira_component == jira_component for item in cls)