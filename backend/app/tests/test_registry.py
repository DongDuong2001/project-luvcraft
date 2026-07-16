import pytest
from app.collectors import CollectorRegistry
from app.collectors.youtube import YouTubeCollector
from app.collectors.community import CommunityCollector
from app.collectors.hype import HypeCollector
from app.collectors.social import SocialCollector
from app.collectors.collector_base import BaseCollector

def test_registry_holds_default_collectors():
    assert CollectorRegistry.get_class("youtube") == YouTubeCollector
    assert CollectorRegistry.get_class("community") == CommunityCollector
    assert CollectorRegistry.get_class("hype") == HypeCollector
    assert CollectorRegistry.get_class("social") == SocialCollector

def test_registry_create_instantiates_correct_collector():
    # Test hype collector instantiation
    hype = CollectorRegistry.create("hype")
    assert isinstance(hype, HypeCollector)
    assert isinstance(hype, BaseCollector)

    # Test social collector instantiation
    social = CollectorRegistry.create("social")
    assert isinstance(social, SocialCollector)
    assert isinstance(social, BaseCollector)

    # Test youtube collector instantiation
    youtube = CollectorRegistry.create("youtube", api_key="dummy-key")
    assert isinstance(youtube, YouTubeCollector)
    assert youtube.api_key == "dummy-key"

def test_registry_decorator():
    @CollectorRegistry.register("test_collector")
    class DummyTestCollector(BaseCollector):
        def _collect(self, **kwargs):
            return []

    assert CollectorRegistry.get_class("test_collector") == DummyTestCollector
    dummy = CollectorRegistry.create("test_collector")
    assert isinstance(dummy, DummyTestCollector)

    # Clean up test collector
    if "test_collector" in CollectorRegistry._registry:
        del CollectorRegistry._registry["test_collector"]

def test_registry_raises_on_unregistered():
    with pytest.raises(KeyError):
        CollectorRegistry.get_class("non_existent")

    with pytest.raises(KeyError):
        CollectorRegistry.create("non_existent")
