import os
import logging
import eventlet
import signal
import sys

logger = logging.getLogger("flickrsmartsync")

EXT_IMAGE = ('jpg', 'png', 'jpeg', 'gif', 'bmp')
EXT_VIDEO = ('avi', 'wmv', 'mov', 'mp4', '3gp', 'ogg', 'ogv', 'mts')


class Sync(object):

    def __init__(self, cmd_args, local, remote):
        global EXT_IMAGE, EXT_VIDEO
        self.pool = eventlet.GreenPool()
        self.cmd_args = cmd_args
        # Create local and remote objects
        self.local = local
        self.remote = remote
        # Ignore extensions
        if self.cmd_args.ignore_ext:
            extensions = self.cmd_args.ignore_ext.split(',')
            EXT_IMAGE = filter(lambda e: e not in extensions, EXT_IMAGE)
            EXT_VIDEO = filter(lambda e: e not in extensions, EXT_VIDEO)
        # Handles KeyboardInterrupt events (CTRL-C or Delete) avoiding data loss during transfers
        signal.signal(signal.SIGINT, self.signal_handler)
        self.stopping_transfers = False

    def start_sync(self):
        # Do the appropriate one time sync
        if self.cmd_args.download:
            self.download()
        elif self.cmd_args.sync_from:
            self.sync()
        else:
            self.upload()
            logger.info('Upload done')
            if self.cmd_args.monitor:
                self.local.watch_for_changes(self.upload)
                self.local.wait_for_quit()

    def sync(self):
        if self.cmd_args.sync_from == "all":
            local_photo_sets = self.local.build_photo_sets(self.cmd_args.sync_path, EXT_IMAGE + EXT_VIDEO)
            remote_photo_sets = self.remote.get_photo_sets()
            # First download complete remote sets that are not local
            for remote_photo_set in remote_photo_sets:
                local_photo_set = os.path.join(self.cmd_args.sync_path, remote_photo_set).replace("/", os.sep)
                if local_photo_set not in local_photo_sets:
                    # TODO: will generate info messages if photo_set is a prefix to other set names
                    self.cmd_args.download = local_photo_set
                    self.download()
            # Now walk our local sets
            for local_photo_set in sorted(local_photo_sets):
                remote_photo_set = local_photo_set.replace(self.cmd_args.sync_path, '').replace("/", os.sep)
                if remote_photo_set not in remote_photo_sets:
                    # doesn't exist remotely, so all files need uploading
                    remote_photos = {}
                else:
                    # filter by what exists remotely, this is a dict of filename->id
                    remote_photos = self.remote.get_photos_in_set(remote_photo_set, get_url=True)
                local_photos = [photo for photo, file_stat in sorted(local_photo_sets[local_photo_set])]
                # download what doesn't exist locally
                photos_to_download = [photo for photo in remote_photos if photo not in local_photos]
                for p in photos_to_download:
                    if self.stopping_transfers:
                        break
                    self.pool.spawn(self.remote.download, remote_photos[p], os.path.join(local_photo_set, p))
                self.pool.waitall()

                # upload what doesn't exist remotely
                photos_to_upload = [photo for photo in local_photos if photo not in remote_photos]
                for p in photos_to_upload:
                    if self.stopping_transfers:
                        break
                    self.pool.spawn(self.remote.upload, os.path.join(local_photo_set, p), p, remote_photo_set)
                self.pool.waitall()
        else:
            logger.warning("Unsupported sync option: %s" % self.cmd_args.sync_from)

    def download(self):
        # Download to corresponding paths
        for photo_set in self.remote.get_photo_sets():
            if photo_set and (self.cmd_args.download == '.' or photo_set.startswith(self.cmd_args.download)):
                folder = os.path.join(self.cmd_args.sync_path, photo_set)
                logger.info('Getting photos in set [%s]' % photo_set)
                photos = self.remote.get_photos_in_set(photo_set, get_url=True)
                # If Uploaded on unix and downloading on windows & vice versa
                if self.cmd_args.is_windows:
                    folder = folder.replace('/', os.sep)

                for photo in photos:
                    if self.stopping_transfers:
                        logger.info('To avoid data loss, the process will be terminated once ongoing transfers complete')
                        self.pool.waitall()
                        return
                    # Adds skips
                    if self.cmd_args.ignore_images and photo.split('.').pop().lower() in EXT_IMAGE:
                        continue
                    elif self.cmd_args.ignore_videos and photo.split('.').pop().lower() in EXT_VIDEO:
                        continue

                    path = os.path.join(folder, photo)
                    if os.path.exists(path):
                        logger.info('Skipped [%s/%s] already downloaded' % (photo_set, photo))
                    else:
                        logger.info('Downloading photo [%s/%s]' % (photo_set, photo))
                        self.pool.spawn(self.remote.download, photos[photo], path)
        self.pool.waitall()

    def upload(self, specific_path=None):
        if specific_path is None:
            only_dir = self.cmd_args.sync_path
        else:
            only_dir = os.path.dirname(specific_path)
        photo_sets = self.local.build_photo_sets(only_dir, EXT_IMAGE + EXT_VIDEO)
        logger.info('Found %s photo sets' % len(photo_sets))

        if specific_path is None:
            # Show custom set titles
            if self.cmd_args.custom_set:
                for photo_set in photo_sets:
                    logger.info('Set Title: [%s]  Path: [%s]' % (self.remote.get_custom_set_title(photo_set), photo_set))

                if self.cmd_args.custom_set_debug and raw_input('Is this your expected custom set titles (y/n):') != 'y':
                    exit(0)

        # Loop through all local photo set map and
        # upload photos that does not exists in online map
        for photo_set in sorted(photo_sets):
            folder = photo_set.replace(self.cmd_args.sync_path, '')
            display_title = self.remote.get_custom_set_title(photo_set)
            logger.info('Getting photos in set [%s]' % display_title)
            photos = self.remote.get_photos_in_set(folder)
            logger.info('Found %s photos' % len(photos))

            for photo, file_stat in sorted(photo_sets[photo_set]):
                if self.stopping_transfers:
                        logger.info('To avoid data loss, the process will be terminated once ongoing transfers complete')
                        self.pool.waitall()
                        return

                # Adds skips
                if self.cmd_args.ignore_images and photo.split('.').pop().lower() in EXT_IMAGE:
                    continue
                elif self.cmd_args.ignore_videos and photo.split('.').pop().lower() in EXT_VIDEO:
                    continue

                if photo in photos or self.cmd_args.is_windows and photo.replace(os.sep, '/') in photos:
                    logger.info('Skipped [%s] already exists in set [%s]' % (photo, display_title))
                else:
                    logger.info('Uploading [%s] to set [%s]' % (photo, display_title))
                    if file_stat.st_size >= 1073741824:
                        logger.error('Skipped [%s] over size limit' % photo)
                        continue
                    file_path = os.path.join(photo_set, photo)
                    gthread = self.pool.spawn(self.remote.upload, file_path, photo, folder)
                    gthread.link(self.uploaded, photo, photos)

            self.pool.waitall()

    @staticmethod
    def uploaded(gt, *args, **kwargs):
        photo = args[0]
        photos = args[1]
        photo_id = gt.wait()
        if photo_id:
            photos[photo] = photo_id

    def signal_handler(self, signal, frame):
        if self.stopping_transfers:
            logger.info("Please be patient, the process will be terminated soon.")
        else:
            print ("Stopping current operation... please wait to avoid corrupted data")
            self.stopping_transfers = True