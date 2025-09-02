"""Video Document Handler Implementation.

This module provides the DocumentHandler implementation for video files,
handling conversion from various video formats to DITA archive format.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

from orlando_toolkit.core.plugins.interfaces import DocumentHandlerBase, ProgressCallback
from orlando_toolkit.core.models import DitaContext

logger = logging.getLogger(__name__)


class VideoDocumentHandler(DocumentHandlerBase):
    """Document handler for video files.
    
    Handles conversion of various video formats (MP4, AVI, MOV, etc.) 
    to DITA archive format with embedded video elements.
    """
    
    def __init__(self) -> None:
        """Initialize video document handler."""
        self._plugin_config: Dict[str, Any] = {}
        self._supported_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.webm', '.mkv']
        
    def can_handle(self, file_path: Path) -> bool:
        """Check if file is a supported video format.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file is a supported video format, False otherwise
        """
        if not file_path or not file_path.exists():
            return False
            
        extension = file_path.suffix.lower()
        return extension in self._supported_extensions
    
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], 
                       progress_callback: Optional[ProgressCallback] = None) -> DitaContext:
        """Convert video file to DITA context.
        
        Args:
            file_path: Path to the video file
            metadata: Conversion metadata and configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            DitaContext containing DITA topics and media files
            
        Raises:
            Exception: If conversion fails
        """
        self.validate_file_exists(file_path)
        
        logger.info(f"Starting video conversion: {file_path}")
        
        # Import video processing components
        from .video_processor import VideoProcessor
        from .dita_builder import VideoDitaBuilder
        
        try:
            # Step 1: Validate video file
            if progress_callback:
                progress_callback("Validating video file...")
            
            processor = VideoProcessor(self._plugin_config)
            if not processor.validate_format(file_path):
                raise ValueError(f"Unsupported or corrupted video file: {file_path}")
            
            # Step 2: Extract video metadata
            if progress_callback:
                progress_callback("Extracting video metadata...")
            
            video_info = processor.extract_metadata(file_path)
            logger.debug(f"Extracted video metadata: {video_info}")
            
            # Step 3: Create DITA structure (no poster generation - KISS principle)
            if progress_callback:
                progress_callback("Creating DITA topics...")
            
            builder = VideoDitaBuilder(metadata, self._plugin_config)
            context = builder.create_dita_context(file_path, video_info, None)
            # Ensure topic titles reflect the video name (without extension)
            try:
                from pathlib import Path as _P
                for fname, topic_el in list(context.topics.items()):
                    title_el = topic_el.find('title') if hasattr(topic_el, 'find') else None
                    if title_el is not None:
                        title_el.text = _P(video_info['filename']).stem
            except Exception:
                pass
            
            if progress_callback:
                progress_callback("Video conversion completed")
            
            logger.info(f"Successfully converted video: {file_path}")
            return context
            
        except Exception as e:
            error_msg = f"Failed to convert video {file_path}: {str(e)}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            raise Exception(error_msg) from e
    
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported video file extensions.
        
        Returns:
            List of supported extensions including the dot
        """
        return self._supported_extensions.copy()
    
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        """Return JSON schema for video conversion metadata.
        
        Returns:
            JSON schema dictionary for validation and UI generation
        """
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": "Video Conversion Settings",
            "description": "Settings for video to DITA conversion",
            "properties": {
                "video_title": {
                    "type": "string",
                    "title": "Video Title",
                    "description": "Custom title for the video topic",
                    "default": ""
                },
                "include_metadata_table": {
                    "type": "boolean", 
                    "title": "Include Metadata Table",
                    "description": "Include technical video metadata in the topic",
                    "default": True
                },
                "generate_poster": {
                    "type": "boolean",
                    "title": "Generate Poster Image",
                    "description": "Generate a poster image from the video",
                    "default": True
                },
                "poster_time_percentage": {
                    "type": "number",
                    "title": "Poster Time (%)",
                    "description": "Time percentage for poster image generation",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 10
                },
                "max_file_size_mb": {
                    "type": "integer",
                    "title": "Maximum File Size (MB)",
                    "description": "Maximum allowed video file size",
                    "minimum": 1,
                    "maximum": 2048,
                    "default": 500
                }
            },
            "additionalProperties": False
        }
    
    def get_handler_info(self) -> Dict[str, Any]:
        """Get detailed information about this handler.
        
        Returns:
            Dictionary with handler information
        """
        return {
            'name': 'Video Document Handler',
            'description': 'Converts video files to DITA format',
            'supported_formats': [
                {'extension': '.mp4', 'description': 'MP4 Video'},
                {'extension': '.avi', 'description': 'AVI Video'},
                {'extension': '.mov', 'description': 'QuickTime Video'},
                {'extension': '.wmv', 'description': 'Windows Media Video'},
                {'extension': '.webm', 'description': 'WebM Video'},
                {'extension': '.mkv', 'description': 'Matroska Video'}
            ],
            'features': [
                'Metadata extraction',
                'Poster image generation', 
                'DITA topic creation',
                'Structure tab integration'
            ],
            'class': self.__class__.__name__,
            'supported_extensions': self.get_supported_extensions(),
            'schema': self.get_conversion_metadata_schema()
        }
    
    def validate_video_constraints(self, file_path: Path) -> None:
        """Validate video file against plugin constraints.
        
        Args:
            file_path: Path to video file
            
        Raises:
            ValueError: If file doesn't meet constraints
        """
        # Check file size
        max_size_mb = self._plugin_config.get('video_processing', {}).get('max_file_size_mb', 500)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        
        if file_size_mb > max_size_mb:
            raise ValueError(f"Video file too large: {file_size_mb:.1f}MB (max: {max_size_mb}MB)")
        
        logger.debug(f"Video file size: {file_size_mb:.1f}MB (within {max_size_mb}MB limit)")
