from .arc_dev import ArcDevScraper
from .base import BaseScraper
from .cutshort import CutshortScraper
from .flexjobs import FlexJobsScraper
from .freshersworld import FreshersworldScraper
from .indeed import IndeedScraper
from .foundit import FounditScraper
from .hirect import HirectScraper
from .hirist import HiristScraper
from .internshala import InternshalaScraper
from .linkedin import LinkedInScraper
from .naukri import NaukriScraper
from .platform_stubs import STUB_SCRAPER_CONFIG, StubPlatformScraper
from .remote_co import RemoteCoScraper
from .relocate_me import RelocateMeScraper
from .remotive import RemotiveScraper
from .shine import ShineScraper
from .simplyhired import SimplyHiredScraper
from .timesjobs import TimesJobsScraper
from .we_work_remotely import WeWorkRemotelyScraper
from .wellfound import WellfoundScraper
from .working_nomads import WorkingNomadsScraper
from .remote_ok import RemoteOkScraper
from .glassdoor import GlassdoorScraper
from .dice import DiceScraper
from .builtin import BuiltInScraper
from .adzuna import AdzunaScraper
from .talent import TalentScraper
from .himalayas import HimalayasScraper
from .jooble import JoobleScraper
from .careerjet import CareerJetScraper
from .just_remote import JustRemoteScraper
from .the_muse import TheMuseScraper
from .jobgether import JobgetherScraper
from .it_org_careers import ITOrgCareersScraper


def build_scraper_registry() -> dict[str, BaseScraper]:
    registry: dict[str, BaseScraper] = {
        "arc_dev": ArcDevScraper(),
        "cutshort": CutshortScraper(),
        "flexjobs": FlexJobsScraper(),
        "freshersworld": FreshersworldScraper(),
        "foundit": FounditScraper(),
        "hirect": HirectScraper(),
        "hirist": HiristScraper(),
        "indeed": IndeedScraper(),
        "internshala": InternshalaScraper(),
        "linkedin": LinkedInScraper(),
        "naukri": NaukriScraper(),
        "remote_co": RemoteCoScraper(),
        "relocate_me": RelocateMeScraper(),
        "remotive": RemotiveScraper(),
        "shine": ShineScraper(),
        "simplyhired": SimplyHiredScraper(),
        "timesjobs": TimesJobsScraper(),
        "we_work_remotely": WeWorkRemotelyScraper(),
        "wellfound": WellfoundScraper(),
        "working_nomads": WorkingNomadsScraper(),
        "remote_ok": RemoteOkScraper(),
        "glassdoor": GlassdoorScraper(),
        "dice": DiceScraper(),
        "builtin": BuiltInScraper(),
        "adzuna": AdzunaScraper(),
        "talent": TalentScraper(),
        "himalayas": HimalayasScraper(),
        "jooble": JoobleScraper(),
        "careerjet": CareerJetScraper(),
        "just_remote": JustRemoteScraper(),
        "the_muse": TheMuseScraper(),
        "jobgether": JobgetherScraper(),
        "it_org_careers": ITOrgCareersScraper(),
    }
    for platform, url in STUB_SCRAPER_CONFIG.items():
        registry[platform] = StubPlatformScraper(platform=platform, start_url=url)
    return registry


__all__ = [
    "ArcDevScraper",
    "CutshortScraper",
    "FlexJobsScraper",
    "FreshersworldScraper",
    "FounditScraper",
    "HirectScraper",
    "HiristScraper",
    "IndeedScraper",
    "InternshalaScraper",
    "LinkedInScraper",
    "NaukriScraper",
    "RemoteCoScraper",
    "RelocateMeScraper",
    "RemotiveScraper",
    "ShineScraper",
    "SimplyHiredScraper",
    "TimesJobsScraper",
    "WeWorkRemotelyScraper",
    "WellfoundScraper",
    "WorkingNomadsScraper",
    "RemoteOkScraper",
    "GlassdoorScraper",
    "DiceScraper",
    "BuiltInScraper",
    "AdzunaScraper",
    "TalentScraper",
    "HimalayasScraper",
    "JoobleScraper",
    "CareerJetScraper",
    "JustRemoteScraper",
    "TheMuseScraper",
    "JobgetherScraper",
    "ITOrgCareersScraper",
    "StubPlatformScraper",
    "build_scraper_registry",
]
