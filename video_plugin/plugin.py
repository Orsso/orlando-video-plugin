"""Main Video Plugin Implementation.

This module provides the primary plugin class that implements the BasePlugin
interface and registers video document handling services with the Orlando
Toolkit plugin system.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from orlando_toolkit.core.plugins.base import BasePlugin, AppContext
from orlando_toolkit.core.plugins.interfaces import UIExtension

logger = logging.getLogger(__name__)

# Export the plugin class explicitly
__all__ = ['VideoConverterPlugin']


class VideoConverterPlugin(BasePlugin, UIExtension):
    """Main video converter plugin for Orlando Toolkit.
    
    This plugin provides video to DITA conversion capabilities including
    document handling, structure tab UI integration, and inline video preview.
    """
    
    def __init__(self, plugin_id: str, metadata: 'PluginMetadata', plugin_dir: str) -> None:
        """Initialize the video converter plugin.
        
        Args:
            plugin_id: Unique identifier for this plugin instance
            metadata: Validated plugin metadata
            plugin_dir: Path to plugin directory
        """
        super().__init__(plugin_id, metadata, plugin_dir)
        self._document_handler: Optional[Any] = None
        
        # Load plugin-specific configuration
        try:
            self.load_config()
            self.log_debug("Video plugin configuration loaded successfully")
        except Exception as e:
            self.log_warning(f"Failed to load plugin configuration: {e}")
            # Continue with default configuration
        
    # Provide default configuration by loading our config.yml
    def _get_default_config(self) -> Dict[str, Any]:
        try:
            import yaml
            config_path = Path(self.plugin_dir) / 'config.yml'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            self.log_warning(f"Using empty default config (error reading config.yml): {e}")
        return {}
        
    def get_name(self) -> str:
        """Get human-readable plugin name."""
        return "Video Library"
    
    def get_description(self) -> str:
        """Get detailed plugin description."""
        return "Convert video files to DITA format with inline preview in structure tab"
    
    def get_version(self) -> str:
        """Get plugin version."""
        return self.metadata.version if self.metadata else "1.0.0"
    
    # -------------------------------------------------------------------------
    # BasePlugin Lifecycle Hooks
    # -------------------------------------------------------------------------
    
    def on_activate(self) -> None:
        """Activate the plugin and register services."""
        super().on_activate()
        
        try:
            # Register document handler service
            from .services.video_handler import VideoDocumentHandler
            self._document_handler = VideoDocumentHandler()
            self._document_handler._plugin_config = self.config
            
            if self.app_context and hasattr(self.app_context, 'service_registry'):
                self.app_context.service_registry.register_document_handler(
                    self._document_handler, self.plugin_id
                )
                self.log_info("Registered Video DocumentHandler service")
            
            # Register UI components if UI registry is available
            if self.app_context and hasattr(self.app_context, 'ui_registry'):
                self.register_ui_components(self.app_context.ui_registry)
                self.log_info("Registered Video UI components")
                
        except Exception as e:
            self.log_error(f"Failed to activate video plugin: {e}")
            raise
    
    def on_deactivate(self) -> None:
        """Deactivate the plugin and cleanup resources."""
        try:
            # Unregister document handler
            if self._document_handler and self.app_context:
                if hasattr(self.app_context, 'service_registry'):
                    self.app_context.service_registry.unregister_service(
                        'DocumentHandler', self.plugin_id
                    )
                    self.log_info("Unregistered Video DocumentHandler service")
                
                # Unregister UI components
                if hasattr(self.app_context, 'ui_registry'):
                    self.unregister_ui_components(self.app_context.ui_registry)
                    self.log_info("Unregistered Video UI components")
                    
                self._document_handler = None
                
        except Exception as e:
            self.log_error(f"Error during video plugin deactivation: {e}")
        
        super().on_deactivate()
    
    # -------------------------------------------------------------------------
    # UIExtension Interface Implementation
    # -------------------------------------------------------------------------
    
    def get_extension_info(self) -> Dict[str, Any]:
        """Get information about this UI extension."""
        return {
            'supported_components': ['panel_factory', 'video_preview'],
            'display_name': 'Video Library UI Extensions',
            'description': 'Video preview panel for structure tab integration'
        }
    
    def register_ui_components(self, ui_registry: Any) -> None:
        """Register UI components with the UI registry."""
        try:
            # Register video preview panel factory for structure tab (PanelFactory object)
            ui_registry.register_panel_factory(
                'video_preview',
                VideoPreviewPanelFactory(self),
                self.plugin_id
            )
            self.log_debug("Registered video preview panel factory")
            
            # Register plugin capabilities
            if hasattr(ui_registry, 'register_plugin_capability'):
                ui_registry.register_plugin_capability(self.plugin_id, "video_preview")
                self.log_debug("Registered video preview capability")

            # Register optional workflow launcher so the plugin controls UX
            try:
                from .ui.launcher import VideoWorkflowLauncher
                if hasattr(ui_registry, 'register_workflow_launcher'):
                    ui_registry.register_workflow_launcher(self.plugin_id, VideoWorkflowLauncher(self))
                    self.log_debug("Registered workflow launcher")
            except Exception as e:
                # Non-fatal: fall back to host's single-file flow
                self.log_warning(f"Could not register workflow launcher: {e}")
                
        except Exception as e:
            self.log_error(f"Failed to register UI components: {e}")
            raise
    
    def unregister_ui_components(self, ui_registry: Any) -> None:
        """Unregister UI components from the UI registry."""
        try:
            # Unregister panel factory
            if hasattr(ui_registry, 'unregister_panel_factory'):
                ui_registry.unregister_panel_factory('video_preview', self.plugin_id)
                self.log_debug("Unregistered video preview panel factory")
            
            # Unregister capabilities
            if hasattr(ui_registry, 'unregister_plugin_capability'):
                ui_registry.unregister_plugin_capability(self.plugin_id, "video_preview")
                self.log_debug("Unregistered video preview capability")

            # Unregister workflow launcher if present
            if hasattr(ui_registry, 'unregister_workflow_launcher'):
                try:
                    ui_registry.unregister_workflow_launcher(self.plugin_id)
                except Exception:
                    pass
                
        except Exception as e:
            self.log_error(f"Failed to unregister UI components: {e}")
    
    def get_panel_factories(self) -> Dict[str, Any]:
        """Get panel factories provided by this extension."""
        return {
            'video_preview': VideoPreviewPanelFactory(self)
        }
    
    def get_marker_providers(self) -> Dict[str, Any]:
        """Get marker providers provided by this extension."""
        # No marker providers for now - keep it simple
        return {}
    
    # -------------------------------------------------------------------------
    # Panel Factory Methods
    # -------------------------------------------------------------------------
    
    # Backward-compatible function retained if older hosts call it
    def create_video_preview_panel(self, parent, **kwargs):
        try:
            from .ui.video_preview_panel import VideoPreviewPanel
            return VideoPreviewPanel(parent, plugin_config=self.config, **kwargs)
        except Exception as e:
            self.log_error(f"Failed to create video preview panel: {e}")
            raise


class VideoPreviewPanelFactory:
    """PanelFactory for Video preview panel with emoji button support."""

    def __init__(self, plugin: 'VideoConverterPlugin') -> None:
        self._plugin = plugin

    def create_panel(self, parent, context=None, **kwargs):
        from .ui.video_preview_panel import VideoPreviewPanel
        return VideoPreviewPanel(
            parent,
            plugin_config=getattr(self._plugin, 'config', {}),
            app_context=context,
            **kwargs,
        )

    def get_panel_type(self) -> str:
        return 'video_preview'

    def get_display_name(self) -> str:
        return 'Video Preview'

    # Optional metadata used by host to render buttons
    def get_button_emoji(self) -> str:
        return '🎬'

    def cleanup_panel(self, panel: Any) -> None:
        try:
            if hasattr(panel, 'cleanup'):
                panel.cleanup()
        except Exception:
            pass

    # Provide defaults if host queries role
    def get_role(self) -> str:
        return 'plugin'

    # Configuration defaults loader
    # Ensure BasePlugin.load_config() creates sensible defaults
    # by overriding _get_default_config in the plugin instance

    # Attach method on plugin class (monkey via instance attribute set in __init__)


    def get_button_emoji(self) -> str:
        # Clapper board emoji for video
        return "\U0001F3AC"

    def cleanup_panel(self, panel) -> None:
        try:
            if hasattr(panel, 'destroy'):
                panel.destroy()
        except Exception:
            pass
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    def log_debug(self, message: str) -> None:
        """Log debug message with plugin context."""
        self.logger.debug(f"[VideoPlugin] {message}")
    
    def log_info(self, message: str) -> None:
        """Log info message with plugin context."""
        self.logger.info(f"[VideoPlugin] {message}")
    
    def log_warning(self, message: str) -> None:
        """Log warning message with plugin context."""
        self.logger.warning(f"[VideoPlugin] {message}")
    
    def log_error(self, message: str) -> None:
        """Log error message with plugin context."""
        self.logger.error(f"[VideoPlugin] {message}")
