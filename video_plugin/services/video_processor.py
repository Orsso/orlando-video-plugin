"""Video Processing Utilities.

This module provides core video processing functionality including
metadata extraction, format validation, and poster image generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile
import os

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Core video processing functionality."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize video processor.
        
        Args:
            config: Plugin configuration dictionary
        """
        self.config = config
        self._logger = logging.getLogger(__name__)
    
    def validate_format(self, video_path: Path) -> bool:
        """Validate video format and codec compatibility.
        
        Args:
            video_path: Path to video file
            
        Returns:
            True if video format is supported and readable
        """
        try:
            import cv2
            
            # Try to open the video with OpenCV
            cap = cv2.VideoCapture(str(video_path))
            
            if not cap.isOpened():
                self._logger.error(f"Cannot open video file: {video_path}")
                return False
            
            # Try to read first frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                self._logger.error(f"Cannot read video frames: {video_path}")
                return False
            
            self._logger.debug(f"Video format validation successful: {video_path}")
            return True
            
        except ImportError:
            self._logger.error("OpenCV not available for video validation")
            return False
        except Exception as e:
            self._logger.error(f"Video validation failed: {e}")
            return False
    
    def extract_metadata(self, video_path: Path) -> Dict[str, Any]:
        """Extract comprehensive video metadata.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary containing video metadata
            
        Raises:
            Exception: If metadata extraction fails
        """
        metadata = {
            'filename': video_path.name,
            'file_size': video_path.stat().st_size,
            'file_size_mb': round(video_path.stat().st_size / (1024 * 1024), 2),
        }
        
        try:
            # Use OpenCV for basic properties
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            
            if cap.isOpened():
                metadata.update({
                    'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    'fps': cap.get(cv2.CAP_PROP_FPS),
                    'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                })
                
                # Calculate duration
                if metadata['fps'] > 0:
                    metadata['duration'] = metadata['frame_count'] / metadata['fps']
                    metadata['duration_formatted'] = self._format_duration(metadata['duration'])
                else:
                    metadata['duration'] = 0
                    metadata['duration_formatted'] = "Unknown"
                
                # Calculate aspect ratio
                if metadata['height'] > 0:
                    aspect_ratio = metadata['width'] / metadata['height']
                    if abs(aspect_ratio - 16/9) < 0.1:
                        metadata['aspect_ratio'] = "16:9"
                    elif abs(aspect_ratio - 4/3) < 0.1:
                        metadata['aspect_ratio'] = "4:3"
                    else:
                        metadata['aspect_ratio'] = f"{aspect_ratio:.2f}:1"
                else:
                    metadata['aspect_ratio'] = "Unknown"
                
                cap.release()
                
            # Try to get additional metadata with PyAV if available
            try:
                self._extract_detailed_metadata(video_path, metadata)
            except Exception as e:
                self._logger.warning(f"Could not extract detailed metadata: {e}")
                
        except ImportError:
            self._logger.error("OpenCV not available for metadata extraction")
            raise Exception("Video processing library not available")
        except Exception as e:
            self._logger.error(f"Metadata extraction failed: {e}")
            raise Exception(f"Failed to extract video metadata: {str(e)}")
        
        # Add format information
        extension = video_path.suffix.lower()
        metadata['format'] = extension.lstrip('.')
        metadata['extension'] = extension
        
        self._logger.info(f"Extracted metadata for {video_path.name}: "
                         f"{metadata['width']}x{metadata['height']}, "
                         f"{metadata['duration_formatted']}, "
                         f"{metadata['file_size_mb']}MB")
        
        return metadata
    
    def _extract_detailed_metadata(self, video_path: Path, metadata: Dict[str, Any]) -> None:
        """Extract detailed metadata using PyAV if available.
        
        Args:
            video_path: Path to video file
            metadata: Metadata dictionary to update
        """
        try:
            import av
            
            with av.open(str(video_path)) as container:
                # Video stream information
                if container.streams.video:
                    video_stream = container.streams.video[0]
                    metadata.update({
                        'codec': video_stream.codec_context.name,
                        'bitrate': video_stream.bit_rate or 0,
                        'pixel_format': video_stream.codec_context.pix_fmt,
                    })
                
                # Audio stream information  
                if container.streams.audio:
                    audio_stream = container.streams.audio[0]
                    metadata.update({
                        'audio_codec': audio_stream.codec_context.name,
                        'audio_channels': audio_stream.codec_context.channels,
                        'audio_sample_rate': audio_stream.codec_context.sample_rate,
                    })
                
                # Container format
                metadata['container_format'] = container.format.name
                
        except ImportError:
            # PyAV not available, use basic metadata
            pass
        except Exception as e:
            self._logger.debug(f"Detailed metadata extraction failed: {e}")
    
    # Poster generation intentionally omitted in first iteration (YAGNI)
    
    def _format_duration(self, duration_seconds: float) -> str:
        """Format duration in seconds to human-readable string.
        
        Args:
            duration_seconds: Duration in seconds
            
        Returns:
            Formatted duration string (e.g., "1:23:45" or "5:30")
        """
        if duration_seconds <= 0:
            return "0:00"
        
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def get_format_info(self, video_path: Path) -> Dict[str, Any]:
        """Get format information for a video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with format information
        """
        extension = video_path.suffix.lower()
        
        format_info = {
            '.mp4': {
                'name': 'MP4',
                'description': 'MPEG-4 Part 14',
                'mime_type': 'video/mp4',
                'common_codecs': ['H.264', 'H.265']
            },
            '.avi': {
                'name': 'AVI', 
                'description': 'Audio Video Interleave',
                'mime_type': 'video/x-msvideo',
                'common_codecs': ['MPEG-4', 'DivX', 'Xvid']
            },
            '.mov': {
                'name': 'MOV',
                'description': 'QuickTime Movie',
                'mime_type': 'video/quicktime', 
                'common_codecs': ['H.264', 'ProRes']
            },
            '.wmv': {
                'name': 'WMV',
                'description': 'Windows Media Video',
                'mime_type': 'video/x-ms-wmv',
                'common_codecs': ['WMV', 'VC-1']
            },
            '.webm': {
                'name': 'WebM',
                'description': 'WebM Video',
                'mime_type': 'video/webm',
                'common_codecs': ['VP8', 'VP9']
            },
            '.mkv': {
                'name': 'MKV',
                'description': 'Matroska Video',
                'mime_type': 'video/x-matroska',
                'common_codecs': ['H.264', 'H.265', 'VP9']
            }
        }
        
        return format_info.get(extension, {
            'name': extension.upper().lstrip('.'),
            'description': f'{extension.upper().lstrip(".")} Video',
            'mime_type': 'video/unknown',
            'common_codecs': []
        })
