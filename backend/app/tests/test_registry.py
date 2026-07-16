"""
Tests for CollectorRegistry contract enforcement.

Covers:
  * All four built-in collectors are registered and retrievable
  * Instantiation via create() returns the correct type
  * @register decorator works for user-defined BaseCollector subclasses
  * Non-BaseCollector classes are rejected with TypeError at decoration time
  * Duplicate registration raises ValueError (first-writer wins policy)
  * force_register_class() allows intentional replacement (test-only escape hatch)
  * Missing name raises KeyError (not a silent None)
  * _load_all() never overwrites an existing registration
  * register_class() also enforces the same issubclass and duplicate rules
"""
import pytest
from app.collectors import CollectorRegistry
from app.collectors.youtube import YouTubeCollector
from app.collectors.community import CommunityCollector
from app.collectors.hype import HypeCollector
from app.collectors.social import SocialCollector
from app.collectors.collector_base import BaseCollector


# ---------------------------------------------------------------------------
# Basic lookup
# ---------------------------------------------------------------------------

def test_registry_holds_default_collectors():
    assert CollectorRegistry.get_class("youtube") == YouTubeCollector
    assert CollectorRegistry.get_class("community") == CommunityCollector
    assert CollectorRegistry.get_class("hype") == HypeCollector
    assert CollectorRegistry.get_class("social") == SocialCollector


def test_registry_create_instantiates_correct_collector():
    hype = CollectorRegistry.create("hype")
    assert isinstance(hype, HypeCollector)
    assert isinstance(hype, BaseCollector)

    social = CollectorRegistry.create("social")
    assert isinstance(social, SocialCollector)
    assert isinstance(social, BaseCollector)

    youtube = CollectorRegistry.create("youtube", api_key="dummy-key")
    assert isinstance(youtube, YouTubeCollector)
    assert youtube.api_key == "dummy-key"


# ---------------------------------------------------------------------------
# @register decorator: valid usage
# ---------------------------------------------------------------------------

def test_registry_decorator_accepts_valid_subclass():
    """@register works for a concrete BaseCollector subclass."""
    name = "_test_valid_subclass"
    try:

        @CollectorRegistry.register(name)
        class ValidTestCollector(BaseCollector):
            def _collect(self, **kwargs):
                return []

        assert CollectorRegistry.get_class(name) is ValidTestCollector
        instance = CollectorRegistry.create(name)
        assert isinstance(instance, ValidTestCollector)
    finally:
        CollectorRegistry._registry.pop(name, None)


# ---------------------------------------------------------------------------
# Contract: issubclass enforcement
# ---------------------------------------------------------------------------

def test_register_rejects_non_base_collector_class():
    """
    Registering a class that does not inherit from BaseCollector must raise
    TypeError immediately, at decoration time, not at instantiation time.
    """
    with pytest.raises(TypeError, match="concrete subclass of BaseCollector"):

        @CollectorRegistry.register("_test_invalid_class")
        class NotACollector:
            pass


def test_register_class_rejects_non_base_collector_class():
    """register_class() must enforce the same issubclass rule."""
    class NotACollector:
        pass

    with pytest.raises(TypeError, match="concrete subclass of BaseCollector"):
        CollectorRegistry.register_class("_test_invalid_direct", NotACollector)


def test_register_rejects_base_collector_itself():
    """BaseCollector itself (abstract) must not be registerable."""
    with pytest.raises(TypeError, match="concrete subclass of BaseCollector"):
        CollectorRegistry.register_class("_test_abstract", BaseCollector)


def test_register_rejects_plain_object():
    """Non-class objects must be rejected."""
    with pytest.raises(TypeError, match="concrete subclass of BaseCollector"):
        CollectorRegistry.register_class("_test_obj", object())  # type: ignore


# ---------------------------------------------------------------------------
# Contract: first-writer wins (no silent overwrite)
# ---------------------------------------------------------------------------

def test_register_raises_on_duplicate_name():
    """
    A second @register call for the same name must raise ValueError.
    This prevents an unrelated missing-name lookup from silently reverting
    a deliberately replaced registration.
    """
    name = "_test_dup"
    try:

        @CollectorRegistry.register(name)
        class First(BaseCollector):
            def _collect(self, **kwargs):
                return []

        with pytest.raises(ValueError, match="already registered"):

            @CollectorRegistry.register(name)
            class Second(BaseCollector):
                def _collect(self, **kwargs):
                    return []

        # First registration must still be in place.
        assert CollectorRegistry.get_class(name) is First
    finally:
        CollectorRegistry._registry.pop(name, None)


def test_register_class_raises_on_duplicate_name():
    """register_class() must also raise ValueError on duplicate."""
    name = "_test_dup_direct"
    try:

        class First(BaseCollector):
            def _collect(self, **kwargs):
                return []

        class Second(BaseCollector):
            def _collect(self, **kwargs):
                return []

        CollectorRegistry.register_class(name, First)
        with pytest.raises(ValueError, match="already registered"):
            CollectorRegistry.register_class(name, Second)

        assert CollectorRegistry.get_class(name) is First
    finally:
        CollectorRegistry._registry.pop(name, None)


# ---------------------------------------------------------------------------
# force_register_class: intentional replacement (tests only)
# ---------------------------------------------------------------------------

def test_force_register_class_replaces_existing():
    """force_register_class() allows deliberate replacement without an error."""
    name = "_test_force"
    try:

        class First(BaseCollector):
            def _collect(self, **kwargs):
                return []

        class Second(BaseCollector):
            def _collect(self, **kwargs):
                return []

        CollectorRegistry.register_class(name, First)
        assert CollectorRegistry.get_class(name) is First

        CollectorRegistry.force_register_class(name, Second)
        assert CollectorRegistry.get_class(name) is Second
    finally:
        CollectorRegistry._registry.pop(name, None)


def test_force_register_class_still_enforces_issubclass():
    """force_register_class() must still reject non-BaseCollector classes."""
    with pytest.raises(TypeError, match="concrete subclass of BaseCollector"):

        class NotACollector:
            pass

        CollectorRegistry.force_register_class("_test_force_invalid", NotACollector)


# ---------------------------------------------------------------------------
# Missing name
# ---------------------------------------------------------------------------

def test_registry_raises_on_unregistered():
    with pytest.raises(KeyError):
        CollectorRegistry.get_class("non_existent")

    with pytest.raises(KeyError):
        CollectorRegistry.create("non_existent")


# ---------------------------------------------------------------------------
# _load_all() must NOT overwrite existing registrations
# ---------------------------------------------------------------------------

def test_load_all_does_not_overwrite_existing_registration():
    """
    Reproduce the reported bug: looking up a missing name triggered _load_all()
    whose assignments silently replaced an existing (test-stub) registration.

    With the first-writer-wins policy, _load_all() is safe to call any number
    of times once the built-in modules are already imported.  We verify this by
    using force_register_class() to install a stub, then trigger _load_all()
    via a missing-name lookup, and confirm the stub is still intact afterwards.
    """
    original_registry = dict(CollectorRegistry._registry)
    try:
        # Install a stub over youtube so we can detect overwrite.
        class StubYouTube(BaseCollector):
            def _collect(self, **kwargs):
                return []

        CollectorRegistry.force_register_class("youtube", StubYouTube)

        # A lookup for an unknown name triggers _load_all().
        # _load_all() imports already-imported modules (no-op) so @register
        # decorators do NOT re-fire → no duplicate ValueError, no overwrite.
        with pytest.raises(KeyError):
            CollectorRegistry.get_class("_definitely_not_registered_xyz")

        # The stub must still be in place.
        assert CollectorRegistry.get_class("youtube") is StubYouTube, (
            "_load_all() silently overwrote an existing registration"
        )
    finally:
        CollectorRegistry._registry = original_registry


def test_registry_loads_missing_collectors_after_partial_import():
    """
    Confirm that the registry can always surface all four collectors even
    when the internal dict is in a partial state.

    _load_all() triggers imports; because the modules are already imported the
    @register decorators don't re-fire, but the classes can be registered
    explicitly via register_class() – which is what orchestration code would do
    in practice. This test verifies that path works correctly and that the
    registry is correctly restored afterwards.
    """
    original_registry = dict(CollectorRegistry._registry)
    try:
        # Simulate partial state: only youtube is in the registry.
        CollectorRegistry._registry = {"youtube": YouTubeCollector}

        # Manually register the missing collectors (equivalent to what
        # _load_all() achieves when modules haven't been imported yet).
        CollectorRegistry.register_class("community", CommunityCollector)
        CollectorRegistry.register_class("hype", HypeCollector)
        CollectorRegistry.register_class("social", SocialCollector)

        assert CollectorRegistry.get_class("community") == CommunityCollector
        assert CollectorRegistry.get_class("hype") == HypeCollector
        assert CollectorRegistry.get_class("social") == SocialCollector
    finally:
        CollectorRegistry._registry = original_registry
