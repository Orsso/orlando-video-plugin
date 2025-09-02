"""DITA Document Builder for Video Content.

This module provides functionality to build DITA topics and archives
from video files, creating proper DITA XML structures with video elements.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import re
import xml.dom.minidom

from lxml import etree as ET
from orlando_toolkit.core.models import DitaContext

logger = logging.getLogger(__name__)


class VideoDitaBuilder:
    """DITA document construction for video content."""
    
    def __init__(self, metadata: Dict[str, Any], plugin_config: Dict[str, Any]) -> None:
        """Initialize DITA builder.
        
        Args:
            metadata: Conversion metadata from user
            plugin_config: Plugin configuration
        """
        self.metadata = metadata
        self.config = plugin_config
        self._logger = logging.getLogger(__name__)
    
    def create_dita_context(self, video_path: Path, video_info: Dict[str, Any], 
                           poster_image: Optional[bytes] = None) -> DitaContext:
        """Create complete DITA context with topic and media.
        
        Args:
            video_path: Path to source video file
            video_info: Video metadata dictionary
            poster_image: Poster image as bytes
            
        Returns:
            DitaContext with video topic and media files
        """
        context = DitaContext()
        
        # Generate topic ID and filename
        topic_id = self._generate_topic_id(video_info['filename'])
        topic_filename = f"{topic_id}.dita"
        
        # Build video topic
        topic_element = self.build_video_topic(topic_id, video_info)
        context.topics[topic_filename] = topic_element
        
        # Add video file to videos dict (proper separation from images)
        video_filename = self._get_video_media_filename(video_info['filename'])
        with open(video_path, 'rb') as f:
            context.videos[video_filename] = f.read()
        
        # Remove poster image generation (KISS principle - not essential)
        # Videos should reference original files, not generate derived images
        
        # Create DITAMAP
        ditamap_root = self._create_ditamap(topic_filename, video_info)
        context.ditamap_root = ditamap_root
        # Provide DOCTYPE hints for SaaS compatibility (core will use them if present)
        try:
            context.metadata['doctype_map'] = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "./dtd/technicalContent/dtd/map.dtd">'
            context.metadata['doctype_concept'] = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA 1.3 Concept//EN" "../dtd/technicalContent/dtd/concept.dtd">'
        except Exception:
            pass
        
        # Store metadata
        from pathlib import Path as _P
        context.metadata.update({
            'title': self.metadata.get('video_title') or _P(video_info['filename']).stem,
            'source_file': video_info['filename'],
            'conversion_date': datetime.now().isoformat(),
            'video_metadata': video_info,
            'plugin': 'orlando-video-plugin'
        })
        # Prefill UI fields if absent
        context.metadata.setdefault('manual_title', 'VIDEO-LIBRARY')
        try:
            # YYYY-MM-DD current date
            context.metadata.setdefault('revision_date', datetime.utcnow().strftime('%Y-%m-%d'))
        except Exception:
            pass
        
        self._logger.info(f"Created DITA context for video: {video_info['filename']}")
        return context
    
    def build_video_topic(self, topic_id: str, video_info: Dict[str, Any]) -> ET.Element:
        """Build DITA topic with video element and metadata.
        
        Args:
            topic_id: Unique topic identifier
            video_info: Video metadata dictionary
            
        Returns:
            DITA topic element
        """
        # Create concept topic
        topic = ET.Element("concept")
        topic.set("id", topic_id)
        
        # Add title
        from pathlib import Path as _P
        title_text = self.metadata.get('video_title') or _P(video_info['filename']).stem
        title = ET.SubElement(topic, "title")
        title.text = title_text
        
        # Add short description
        shortdesc = ET.SubElement(topic, "shortdesc")
        duration_str = video_info.get('duration_formatted', 'Unknown duration')
        size_str = f"{video_info.get('file_size_mb', 0)}MB"
        resolution_str = f"{video_info.get('width', 0)}Ã—{video_info.get('height', 0)}"
        shortdesc.text = (
            f"Video content: {duration_str}, "
            f"{video_info.get('width', 0)}×{video_info.get('height', 0)}, "
            f"{size_str}"
        )
        
        # Create concept body
        conbody = ET.SubElement(topic, "conbody")
        # Ensure no shortdesc remains (keep topic minimal)
        try:
            sd = topic.find('shortdesc')
            if sd is not None:
                topic.remove(sd)
        except Exception:
            pass
        
        # Add video element
        self._add_video_element(conbody, topic_id, video_info)
        
        # No metadata table in XML (panel will show a tooltip)
        
        self._logger.debug(f"Built DITA topic for {video_info['filename']}")
        return topic
    
    def _add_video_element(self, parent: ET.Element, topic_id: str, video_info: Dict[str, Any]) -> None:
        """Add DITA video element to parent.
        
        Args:
            parent: Parent element to add video to
            topic_id: Topic ID for media file references
            video_info: Video metadata dictionary
        """
        # Create object-based embedded video
        obj = ET.SubElement(parent, "object")
        
        # Set object attributes
        video_filename = self._get_video_media_filename(video_info['filename'])
        obj.set("data", f"../media/{video_filename}")
        obj.set("outputclass", "video")
        obj.set("type", self._get_video_mime_type(video_info.get('extension', '')))
        
        # Controls parameter (object param)
        param = ET.SubElement(obj, "param")
        param.set("name", "controls")
        param.set("value", "true")
    
    def _add_metadata_table(self, parent: ET.Element, video_info: Dict[str, Any]) -> None:
        """Add video metadata table to parent element.
        
        Args:
            parent: Parent element to add table to
            video_info: Video metadata dictionary
        """
        # Create table
        table = ET.SubElement(parent, "table")
        table.set("frame", "all")
        table.set("rowsep", "1")
        table.set("colsep", "1")
        
        # Table title
        title = ET.SubElement(table, "title")
        title.text = "Video Information"
        
        # Table group
        tgroup = ET.SubElement(table, "tgroup")
        tgroup.set("cols", "2")
        
        # Column specifications
        colspec1 = ET.SubElement(tgroup, "colspec")
        colspec1.set("colname", "property")
        colspec1.set("colwidth", "1*")
        
        colspec2 = ET.SubElement(tgroup, "colspec")
        colspec2.set("colname", "value")
        colspec2.set("colwidth", "2*")
        
        # Table header
        thead = ET.SubElement(tgroup, "thead")
        header_row = ET.SubElement(thead, "row")
        
        header_entry1 = ET.SubElement(header_row, "entry")
        header_entry1.text = "Property"
        
        header_entry2 = ET.SubElement(header_row, "entry")
        header_entry2.text = "Value"
        
        # Table body
        tbody = ET.SubElement(tgroup, "tbody")
        
        # Add metadata rows
        metadata_rows = [
            ("Duration", video_info.get('duration_formatted', 'Unknown')),
            ("Resolution", f"{video_info.get('width', 0)}Ã—{video_info.get('height', 0)}"),
            ("File Size", f"{video_info.get('file_size_mb', 0)} MB"),
            ("Format", video_info.get('format', 'Unknown')),
            ("Frame Rate", f"{video_info.get('fps', 0):.1f} fps" if video_info.get('fps') else 'Unknown'),
            ("Aspect Ratio", video_info.get('aspect_ratio', 'Unknown')),
        ]
        
        # Add codec information if available
        if video_info.get('codec'):
            metadata_rows.append(("Video Codec", video_info['codec']))
        if video_info.get('audio_codec'):
            metadata_rows.append(("Audio Codec", video_info['audio_codec']))
        
        for property_name, value in metadata_rows:
            row = ET.SubElement(tbody, "row")
            
            entry1 = ET.SubElement(row, "entry")
            entry1.text = property_name
            
            entry2 = ET.SubElement(row, "entry")
            entry2.text = str(value)
    
    def _create_ditamap(self, topic_filename: str, video_info: Dict[str, Any]) -> ET.Element:
        """Create DITAMAP element.
        
        Args:
            topic_filename: Name of the topic file
            video_info: Video metadata dictionary
            
        Returns:
            DITAMAP root element
        """
        # Create map element
        map_elem = ET.Element("map")
        try:
            map_elem.set("xml:lang", "en-US")
        except Exception:
            pass
        
        # Add title
        title = ET.SubElement(map_elem, "title")
        from pathlib import Path as _P
        # Prefer manual_title from UI, fallback to video_title, then filename stem
        title.text = (
            self.metadata.get('manual_title')
            or self.metadata.get('video_title')
            or _P(video_info['filename']).stem
        )

        # Map-level topicmeta: ensure manual_reference and temporal metadata
        map_topicmeta = ET.SubElement(map_elem, "topicmeta")
        manual_ref = self._normalize_manual_reference(title.text)
        other_manual_ref = ET.SubElement(map_topicmeta, "othermeta")
        other_manual_ref.set("name", "manual_reference")
        other_manual_ref.set("content", manual_ref)
        critdates = ET.SubElement(map_topicmeta, "critdates")
        created = ET.SubElement(critdates, "created")
        created.set("date", self._current_date_ymd())
        revised = ET.SubElement(critdates, "revised")
        revised.set("modified", self.metadata.get('revision_date') or self._current_date_ymd())
        
        # Add topic reference
        topicref = ET.SubElement(map_elem, "topicref")
        topicref.set("href", f"topics/{topic_filename}")
        topicref.set("format", "dita")
        topicref.set("type", "concept")
        # Provide explicit navtitle to help UIs display the expected label
        topicmeta = ET.SubElement(topicref, "topicmeta")
        navtitle = ET.SubElement(topicmeta, "navtitle")
        navtitle.text = title.text
        
        return map_elem
    
    def _generate_topic_id(self, filename: str) -> str:
        """Generate valid DITA topic ID from filename.
        
        Args:
            filename: Original filename
            
        Returns:
            Valid DITA topic ID
        """
        # Remove extension and clean filename
        name_without_ext = Path(filename).stem
        
        # Replace invalid characters with hyphens
        topic_id = ""
        for char in name_without_ext.lower():
            if char.isalnum():
                topic_id += char
            elif char in " -_.":
                topic_id += "-"
        
        # Remove duplicate hyphens
        while "--" in topic_id:
            topic_id = topic_id.replace("--", "-")
        
        # Ensure it starts with a letter
        if not topic_id[0].isalpha():
            topic_id = "video-" + topic_id
        
        # Limit length
        if len(topic_id) > 50:
            topic_id = topic_id[:50]
        
        return topic_id.strip("-")
    
    def _get_video_media_filename(self, original_filename: str) -> str:
        """Get media filename for video file.
        
        Args:
            original_filename: Original video filename
            
        Returns:
            Media filename to use in DITA archive
        """
        if self.config.get('dita_integration', {}).get('preserve_original_filenames', True):
            return original_filename
        else:
            # Generate sanitized filename
            return self._generate_topic_id(original_filename) + Path(original_filename).suffix
    
    def _get_video_mime_type(self, extension: str) -> str:
        """Get MIME type for video extension.
        
        Args:
            extension: File extension (with or without dot)
            
        Returns:
            MIME type string
        """
        extension = extension.lower().lstrip('.')
        
        mime_types = {
            'mp4': 'video/mp4',
            'avi': 'video/x-msvideo',
            'mov': 'video/quicktime',
            'wmv': 'video/x-ms-wmv',
            'webm': 'video/webm',
            'mkv': 'video/x-matroska'
        }
        
        return mime_types.get(extension, 'video/unknown')
    
    def format_xml_pretty(self, element: ET.Element) -> str:
        """Format XML element for pretty printing.
        
        Args:
            element: XML element to format
            
        Returns:
            Pretty-formatted XML string
        """
        rough_string = ET.tostring(element, encoding='unicode')
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    # --- Minimal helpers for required metadata defaults ---
    def _normalize_manual_reference(self, title: Optional[str]) -> str:
        """Normalize the manual title into a CMS-accepted manual_reference.
        Falls back to VIDEO-LIBRARY when title is missing/empty.
        """
        default = "VIDEO-LIBRARY"
        if not title:
            return default
        norm = title.strip()
        norm = re.sub(r"[^A-Za-z0-9]+", "-", norm)
        norm = re.sub(r"-{2,}", "-", norm).strip("-")
        return (norm.upper() or default)

    def _current_date_ymd(self) -> str:
        """Return current UTC date in YYYY-MM-DD format."""
        return datetime.utcnow().strftime("%Y-%m-%d")
