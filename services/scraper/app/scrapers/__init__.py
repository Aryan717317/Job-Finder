from .arc_dev import ArcDevScraper
from .base import BaseScraper
from .cutshort import CutshortScraper
from .flexjobs import FlexJobsScraper
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
from .we_work_remotely import WeWorkRemotelyScraper
from .wellfound import WellfoundScraper
from .working_nomads import WorkingNomadsScraper


def build_scraper_registry() -> dict[str, BaseScraper]:
    registry: dict[str, BaseScraper] = {
        "arc_dev": ArcDevScraper(),
        "cutshort": CutshortScraper(),
        "flexjobs": FlexJobsScraper(),
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
        "we_work_remotely": WeWorkRemotelyScraper(),
        "wellfound": WellfoundScraper(),
        "working_nomads": WorkingNomadsScraper(),
    }
    for platform, url in STUB_SCRAPER_CONFIG.items():
        registry[platform] = StubPlatformScraper(platform=platform, start_url=url)
    return registry


__all__ = [
    "ArcDevScraper",
    "CutshortScraper",
    "FlexJobsScraper",
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
    "WeWorkRemotelyScraper",
    "WellfoundScraper",
    "WorkingNomadsScraper",
    "StubPlatformScraper",
    "build_scraper_registry",
]
