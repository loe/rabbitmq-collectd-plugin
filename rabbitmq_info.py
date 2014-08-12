# Name: rabbitmq-collectd-plugin - rabbitmq_info.py
# Author: https://github.com/phrawzty/rabbitmq-collectd-plugin/commits/master
# Description: This plugin uses Collectd's Python plugin to obtain RabbitMQ metrics.
#
# Copyright 2012 Daniel Maher
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collectd
import subprocess
import re


NAME = 'rabbitmq_info'
# Override in config by specifying 'RmqcBin'.
RABBITMQCTL_BIN = '/usr/sbin/rabbitmqctl'
# Override in config by specifying 'PmapBin'
PMAP_BIN = '/usr/bin/pmap'
# Override in config by specifying 'PidofBin'.
PIDOF_BIN = '/bin/pidof'
# Override in config by specifying 'PidFile.
PID_FILE = "/var/run/rabbitmq/pid"
# Override in config by specifying 'Vhost'.
VHOST = "/"
# Override in config by specifying 'Verbose'.
VERBOSE_LOGGING = False


# Obtain the interesting statistical info for each virtual host.
def get_stats():
    stats = {}
    stats['pmap.mapped'] = 0
    stats['pmap.used'] = 0
    stats['pmap.shared'] = 0

    for vhost in list(VHOST):
      stats['ctl.{0}.messages'.format(vhost)] = 0
      stats['ctl.{0}.memory'.format(vhost)] = 0
      stats['ctl.{0}.consumers'.format(vhost)] = 0

      # call rabbitmqctl
      try:
          p = subprocess.Popen([RABBITMQCTL_BIN, '-q', '-p', vhost,
              'list_queues', 'name', 'durable', 'messages', 'memory', 'consumers'],
              shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
      except:
          logger('err', 'Failed to run %s' % RABBITMQCTL_BIN)
          return None

      for line in p.stdout.readlines():
          ctl_stats = line.split()
          try:
              ctl_stats[2] = int(ctl_stats[2])
              ctl_stats[3] = int(ctl_stats[3])
              ctl_stats[4] = int(ctl_stats[4])
          except:
              continue

          # Global metrics
          stats['ctl.{0}.messages'.format(vhost)] += ctl_stats[2]
          stats['ctl.{0}.memory'.format(vhost)] += ctl_stats[3]
          stats['ctl.{0}.consumers'.format(vhost)] += ctl_stats[4]

          # Per-queue metrics only on durable queues.
          if ctl_stats[1] == 'true':
            queue_name = ctl_stats[0]
            stats['ctl.{0}.{1}.messages'.format(vhost, queue_name)] = ctl_stats[2]
            stats['ctl.{0}.{1}.memory'.format(vhost, queue_name)] = ctl_stats[3]
            stats['ctl.{0}.{1}.consumers'.format(vhost, queue_name)] = ctl_stats[4]

      logger('verb', '[%s] Messages: %i, Memory: %i, Consumers: %i' %
        (vhost, stats['ctl.{0}.messages'.format(vhost)], stats['ctl.{0}.memory'.format(vhost)], stats['ctl.{0}.consumers'.format(vhost)]))

    # get the pid of rabbitmq
    try:
        with open(PID_FILE, 'r') as f:
          pid = f.read().strip()
    except:
        logger('err', 'Unable to read %s' % PID_FILE)
        return None

    # use pmap to get proper memory stats
    try:
        p = subprocess.Popen([PMAP_BIN, '-d', pid], shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except:
        logger('err', 'Failed to run %s' % PMAP_BIN)
        return None

    line = p.stdout.readlines()[-1].strip()
    if re.match('mapped', line):
        m = re.match(r"\D+(\d+)\D+(\d+)\D+(\d+)", line)
        stats['pmap.mapped'] = int(m.group(1))
        stats['pmap.used'] = int(m.group(2))
        stats['pmap.shared'] = int(m.group(3))
    else:
        logger('warn', '%s returned something strange.' % PMAP_BIN)
        return None

    logger('verb', '[pmap] Mapped: %i, Used: %i, Shared: %i' %
        (stats['pmap.mapped'], stats['pmap.used'], stats['pmap.shared']))

    return stats


# Config data from collectd
def configure_callback(conf):
    global RABBITMQCTL_BIN, PMAP_BIN, PID_FILE, VERBOSE_LOGGING, VHOST
    for node in conf.children:
        if node.key == 'RmqcBin':
            RABBITMQCTL_BIN = node.values[0]
        elif node.key == 'PmapBin':
            PMAP_BIN = node.values[0]
        elif node.key == 'PidFile':
            PID_FILE = node.values[0]
        elif node.key == 'Verbose':
            VERBOSE_LOGGING = bool(node.values[0])
        elif node.key == 'Vhost':
            VHOST = node.values
        else:
            logger('warn', 'Unknown config key: %s' % node.key)


# Send info to collectd
def read_callback():
    logger('verb', 'read_callback')
    info = get_stats()

    if not info:
        logger('err', 'No information received - very bad.')
        return

    logger('verb', 'About to trigger the dispatch..')

    # send values
    for key in info:
        logger('verb', 'Dispatching %s : %i' % (key, info[key]))
        val = collectd.Values(plugin=NAME)
        val.type = 'gauge'
        val.type_instance = key
        val.values = [int(info[key])]
        val.dispatch()


# Send log messages (via collectd)
def logger(t, msg):
    if t == 'err':
        collectd.error('%s: %s' % (NAME, msg))
    if t == 'warn':
        collectd.warning('%s: %s' % (NAME, msg))
    elif t == 'verb' and VERBOSE_LOGGING == True:
        collectd.info('%s: %s' % (NAME, msg))


# Runtime
collectd.register_config(configure_callback)
collectd.warning('Initialising rabbitmq_info')
collectd.register_read(read_callback)
