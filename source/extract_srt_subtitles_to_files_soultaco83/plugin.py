#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    Written by:               Modified by Soultaco83
    Date:                     08-29-2024

    Copyright:
        Copyright (C) 2024 Soultaco83

        This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
        Public License as published by the Free Software Foundation, version 3.

        This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
        implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
        for more details.

        You should have received a copy of the GNU General Public License along with this program.
        If not, see <https://www.gnu.org/licenses/>.

"""
import logging
import os
import re
import glob

from unmanic.libs.unplugins.settings import PluginSettings
from unmanic.libs.directoryinfo import UnmanicDirectoryInfo

from extract_srt_subtitles_to_files_soultaco83.lib.ffmpeg import StreamMapper, Probe, Parser

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.extract_srt_subtitles_to_files_soultaco83")

class Settings(PluginSettings):
    settings = {
        "languages_to_extract": "",
        "extract_regardless": False
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)

        self.form_settings = {
            "languages_to_extract": {
                "label": "Subtitle languages to extract (leave empty for all)",
            },
            "extract_regardless": {
                "label": "Extract regardless if srt file exists, if already processed via a .unmanic, or SRT_SUB existing",
            },
        }

class PluginStreamMapper(StreamMapper):
    def __init__(self):
        super(PluginStreamMapper, self).__init__(logger, ['subtitle'])
        self.sub_streams = []
        self.settings = None
        logger.debug("PluginStreamMapper initialized.")

    def set_settings(self, settings):
        self.settings = settings
        logger.debug("Settings have been set in PluginStreamMapper: %s", settings)

    def _get_language_list(self):
        language_list = self.settings.get_setting('languages_to_extract')
        language_list = re.sub(r'\s', '-', language_list)
        languages = list(filter(None, language_list.lower().split(',')))
        logger.debug("Languages to extract: %s", languages)
        return [language.strip() for language in languages]

    def test_stream_needs_processing(self, stream_info: dict):
        """Any text-based subtitles will need to be processed"""
        codec_name = stream_info.get('codec_name', '').lower()
        if codec_name not in ['srt', 'mov_txt', 'subrip']:
            logger.debug("Stream %s does not require processing (codec: %s).", stream_info.get('index'), codec_name)
            return False

        languages = self._get_language_list()

        language_tag = stream_info.get('tags', {}).get('language', '').lower()
        logger.debug("Checking if stream with language '%s' needs processing.", language_tag)

        # If no languages specified, extract all
        if len(languages) == 0:
            logger.debug("No specific languages set; all subtitle streams will be processed.")
            return True

        if language_tag in languages:
            logger.debug("Stream language '%s' is in the extraction list.", language_tag)
            return True
        else:
            logger.debug("Stream language '%s' is not in the extraction list; skipping.", language_tag)
            return False

    def custom_stream_mapping(self, stream_info: dict, stream_id: int):
        stream_tags = stream_info.get('tags', {})
        
        # e.g. 'eng', 'fra'
        language_tag = stream_tags.get('language', '').lower()
        logger.debug("Processing stream ID %d with language tag '%s'.", stream_id, language_tag)
        
        languages = self._get_language_list()
        
        # Skip stream if not in the specified languages
        if len(languages) > 0 and language_tag not in languages:
            logger.debug("Stream ID %d with language '%s' is not in the extraction list; skipping mapping.", stream_id, language_tag)
            return {
                'stream_mapping':  [],
                'stream_encoding': [],
            }
        
        # Generate subtitle tag
        # We only use the language tag and append a number (_1, _2, etc.)
        subtitle_tag = language_tag  # Keep only the language code (e.g., 'eng')
        logger.debug("Generated subtitle tag '%s' for stream ID %d.", subtitle_tag, stream_id)
        
        # Use a more robust stream specifier
        stream_specifier = f'0:s:{stream_id}?'
        
        # Add the stream to the list
        self.sub_streams.append(
            {
                'stream_id': stream_id,
                'subtitle_tag': subtitle_tag,
                'stream_mapping': ['-map', stream_specifier],
            }
        )
        logger.debug("Added stream ID %d to sub_streams with tag '%s'.", stream_id, subtitle_tag)
        
        # Copy the streams to the destination
        mapping = {
            'stream_mapping': ['-map', stream_specifier],
            'stream_encoding': ['-c:s:{}'.format(stream_id), 'copy'],
        }
        logger.debug("Stream mapping for stream ID %d: %s", stream_id, mapping)
        return mapping

    def get_ffmpeg_args(self):
        """
        Overwrite default function. We only need the first lot of args.
        :return: list of ffmpeg arguments
        """
        args = []

        # Add generic options first
        args += self.generic_options
        logger.debug("Added generic options: %s", self.generic_options)

        # Add the input file
        if not self.input_file:
            logger.error("Input file has not been set in PluginStreamMapper.")
            raise Exception("Input file has not been set")
        args += ['-i', self.input_file]
        logger.debug("Added input file to ffmpeg args: %s", self.input_file)

        # Add other main options
        args += self.main_options
        logger.debug("Added main options: %s", self.main_options)

        # Add advanced options (stream mapping and encoding args)
        args += self.advanced_options
        logger.debug("Added advanced options: %s", self.advanced_options)

        logger.debug("Final ffmpeg args from get_ffmpeg_args: %s", args)
        return args

def srt_already_extracted(settings, path):
    logger.debug("Checking if srt is already extracted for file: %s", path)

    # Check .unmanic file if it exists
    unmanic_file_path = os.path.join(os.path.dirname(path), '.unmanic')
    if os.path.exists(unmanic_file_path):
        directory_info = UnmanicDirectoryInfo(os.path.dirname(path))
        try:
            already_extracted = directory_info.get('extract_srt_subtitles_to_files', os.path.basename(path))
            if already_extracted:
                logger.debug(f"File's srt subtitle streams were previously extracted according to .unmanic file: {already_extracted}")
                return True
        except Exception as e:
            logger.debug(f"Error reading .unmanic file: {str(e)}")

    probe = Probe(logger, allowed_mimetypes=['video'])
    if not probe.file(path):
        logger.debug("File '%s' is not a video file.", path)
        return False

    # Retrieve the format tags (where srt_SUB is located)
    format_tags = probe.get('format', {}).get('tags', {})
    subs_tag = format_tags.get('srt_SUB', '').lower()
    
    logger.debug("srt_SUB tag value for file '%s': '%s'", path, subs_tag)
    
    # Check if the file has srt, SubRip, or MOV_TEXT subtitles
    has_target_subtitles = False
    streams = probe.get('streams', [])
    for stream in streams:
        if stream.get('codec_type') == 'subtitle':
            codec_name = stream.get('codec_name', '').lower()
            if codec_name in ['srt', 'mov_txt', 'subrip']:
                has_target_subtitles = True
                break

    # Check for existing srt files
    base_path = os.path.splitext(path)[0]
    existing_srt_files = glob.glob(f"{base_path}.*.srt")
    if settings.get_setting('extract_regardless'):
        logger.debug("Plugin configured to extract regardless of previous extraction")
        return False
    elif subs_tag == 'extracted' and existing_srt_files:
        logger.debug(f"srt subtitles have already been extracted and tagged for file '{path}'. Skipping further processing.")
        return True
    elif existing_srt_files:
        logger.debug(f"srt files exist for file '{path}'. Skipping extraction due to existing srt files.")
        return True
    elif not existing_srt_files and not subs_tag == 'extracted' and has_target_subtitles:
        logger.debug(f"No srt files or srt_SUB tag, but target subtitles found for file '{path}'. Proceeding with subtitle extraction.")
        return False
    else:
        logger.debug(f"No srt subtitles to extract for file '{path}'. Skipping further processing.")
        return True

def on_library_management_file_test(data):
    """
    Runner function - enables additional actions during the library management file tests.
    """
    abspath = data.get('path')
    logger.debug("Running on_library_management_file_test for path: %s", abspath)
    
    # Configure settings object
    settings = Settings(library_id=data.get('library_id', None))
    logger.debug("Initialized settings with library_id: %s", data.get('library_id', None))

    # Check if subtitles need to be extracted
    if not srt_already_extracted(settings, abspath):
        data['add_file_to_pending_tasks'] = True
        logger.debug(f"File '{abspath}' is added to pending tasks. It needs subtitle extraction.")
    else:
        logger.debug(f"File '{abspath}' is not added to pending tasks. No subtitle extraction needed.")
    
    return data

import subprocess  # Add this import

def get_unique_srt_filename(base_path, subtitle_tag, stream_index):
    """
    Generate a unique srt filename with Unmanic prefix.
    """
    srt_filename = f"{base_path}.unmanic.{subtitle_tag}.{stream_index}.srt"
    logger.debug(f"Generated srt filename: {srt_filename}")
    return srt_filename

def on_worker_process(data):
    """
    Runner function - enables additional configured processing jobs during the worker stages of a task.
    """
    logger.debug("Running on_worker_process for data: %s", data)
    
    # Default to no FFMPEG command required
    data['exec_command'] = []
    data['repeat'] = False

    # Get the path to the file
    abspath = data.get('file_in')
    logger.debug("Processing worker process for file: %s", abspath)

    # Get file probe
    probe = Probe(logger, allowed_mimetypes=['video'])
    if not probe.file(abspath):
        logger.debug("File '%s' is not a video file.", abspath)
        return data

    # Check if subtitles need to be extracted
    settings = Settings(library_id=data.get('library_id', None))
    logger.debug("Initialized settings with library_id: %s", data.get('library_id', None))
    
    if srt_already_extracted(settings, abspath):  # Corrected function name
        logger.debug("Skipping processing for file '%s' as srt is already extracted or no processing needed.", abspath)
        # Set exec_command to None to signal that no processing is needed
        data['exec_command'] = None
        return data

    # Proceed with the subtitle extraction process
    mapper = PluginStreamMapper()
    mapper.set_settings(settings)
    mapper.set_probe(probe)
    logger.debug("PluginStreamMapper configured for file '%s'.", abspath)

    if mapper.streams_need_processing():
        logger.debug("Streams need processing for file '%s'.", abspath)
        
        # Set the input file
        mapper.set_input_file(abspath)
        logger.debug("Input file set to '%s' in PluginStreamMapper.", abspath)
        
        # Get generated ffmpeg args
        ffmpeg_args = mapper.get_ffmpeg_args()
        logger.debug("Generated ffmpeg args: %s", ffmpeg_args)

        # Add srt extract args
        base_path = os.path.splitext(data.get('original_file_path'))[0]
        logger.debug("Base path: %s", base_path)

        for sub_stream in mapper.sub_streams:
            stream_mapping = sub_stream.get('stream_mapping', [])
            subtitle_tag = sub_stream.get('subtitle_tag')
            stream_index = sub_stream.get('stream_id')
            logger.debug("Processing sub_stream: %s", sub_stream)

            # Get a unique srt filename
            output_srt = get_unique_srt_filename(base_path, subtitle_tag, stream_index)
            logger.debug("srt filename for subtitle tag '%s': %s", subtitle_tag, output_srt)

            ffmpeg_args += stream_mapping          
            ffmpeg_args += [
                "-y",
                output_srt,
            ]
            logger.debug("Updated ffmpeg_args after adding stream mapping and output: %s", ffmpeg_args)

        # Apply ffmpeg args to command
        data['exec_command'] = ['ffmpeg']
        data['exec_command'] += ffmpeg_args
        logger.debug("Final exec_command set to: %s", data['exec_command'])

        # Set the parser
        parser = Parser(logger)
        parser.set_probe(probe)
        data['command_progress_parser'] = parser.parse_progress
        logger.debug("Command progress parser set.")

        # Execute FFmpeg command
        try:
            result = subprocess.run(data['exec_command'], check=True, capture_output=True, text=True)
            logger.debug("FFmpeg command executed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg command failed: {e}")
            logger.debug(f"FFmpeg stderr: {e.stderr}")
            # If the error is due to stream mapping, we can ignore it and continue
            if "Stream map '0:s:" in e.stderr and "matches no streams" in e.stderr:
                logger.warning("Some stream mappings failed, but continuing with metadata update.")
            else:
                return data  # Exit if there's an unexpected error

        # Update metadata after extraction
        temp_output = abspath.replace(".mkv", "_temp.mkv")
        metadata_command = [
            'ffmpeg', '-i', abspath,
            '-map_metadata', '0',
            '-metadata', 'srt_SUB=extracted',
            '-c', 'copy',
            '-y',
            temp_output
        ]
        logger.debug("Metadata command: %s", metadata_command)
        try:
            logger.debug("Running metadata command for file '%s'.", abspath)
            subprocess.run(metadata_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.debug("Metadata command executed successfully.")
            os.replace(temp_output, abspath)
            logger.debug(f"Metadata 'srt_SUB=extracted' added to {abspath} and original file replaced.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set metadata on {abspath}: {str(e)}")
            if e.stderr:
                logger.debug("ffmpeg stderr: %s", e.stderr.decode('utf-8'))
        except OSError as oe:
            logger.error(f"Failed to replace the original file: {str(oe)}")
            logger.debug("OSError details: %s", str(oe))

    else:
        logger.debug("Streams do not need processing for file '%s'.", abspath)

    return data
    