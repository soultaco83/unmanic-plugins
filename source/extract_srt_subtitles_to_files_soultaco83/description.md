Any SRT subtitle streams found in the file will be exported as *.srt files in the same directory as the original file.
The goal of this is to move from the .unmanic file and to use a tag on the file instead. This way if the file was to be updated
via another tool like sonarr or radarr. It would reprocess. This does not remove the .unmanic file in use though currently. 
If there is already a .unmanic file it will look for that first. If extract_srt_subtitles_to_files exists in file for this
video it will skip no matter what like the offical plugin.

:::warning
This plugin is not compatible with linking as the remote link will not have access to the original source file's directory.
I offer no guarantee for this plugin. This works for my use case. Please do tests first.
:::
