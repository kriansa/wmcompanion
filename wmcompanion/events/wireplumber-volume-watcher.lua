-- Copyright (c) 2022 Daniel Pereira
-- 
-- SPDX-License-Identifier: Apache-2.0

-- This is an always-on volume watcher that prints out every volume change to stdout, and it's meant
-- to work with wmcompanion's MainVolumeLevel class.
--
-- To test it, simply run:
--   wpexec wireplumber-volume-watcher.lua

Core.require_api("default-nodes", "mixer", function(default_nodes, mixer)
  -- Use the right scale to display the volume, same used by pulseaudio
  mixer["scale"] = "cubic"

  -- Constants
  VolumeSource = { INPUT = "input", OUTPUT = "output" }
  NodeByInput = { [VolumeSource.INPUT] = "Audio/Source", [VolumeSource.OUTPUT] = "Audio/Sink" }

  -- This is the state of each of the sources
  ENABLED_SOURCES = { [VolumeSource.INPUT] = nil, [VolumeSource.OUTPUT] = nil }

  -- Prints the volume in the following format:
  -- SOURCE(input or output):LEVEL(as decimal):MUTED(true or false):AVAILABILITY(true or false)
  --
  -- * SOURCE is whether that volume is for speakers (output) or microphone (input)
  -- * LEVEL is a decimal betwen 0.00 and 1.00
  -- * MUTED is whether the user has muted the main input/output
  -- * AVAILABILITY is whether the system has or not at least one of that kind of input/output
  function print_volume(source, node_id)
    if ENABLED_SOURCES[source] == false then
      print(string.format("%s:0:false:false", source))
    else
      local volume = mixer:call("get-volume", node_id)
      print(string.format("%s:%.2f:%s:true", source, volume["volume"], volume["mute"]))
    end
  end

  --
  -- Add a watcher for volume level changes
  --
  mixer:connect("changed", function(_, obj_id)
    local default_sink = default_nodes:call("get-default-node", NodeByInput[VolumeSource.OUTPUT])
    if obj_id == default_sink then
      print_volume(VolumeSource.OUTPUT, default_sink)
      return
    end

    local default_source = default_nodes:call("get-default-node", NodeByInput[VolumeSource.INPUT])
    if obj_id == default_source then
      print_volume(VolumeSource.INPUT, default_source)
    end
  end)

  --
  -- Add watcher for sources (input/output) disconnection detection
  --

  -- This function will either turn on or turn off a given device (output or input)
  function set_device_state(source, state)
    if state == true then
      default_node = default_nodes:call("get-default-node", NodeByInput[source])

      -- Workaround: If by some reason the result of this function is INT_MAX, it failed somehow to
      -- fetch the default node, so let's rerun this call after wp_core_sync
      if default_node == 4294967295 then
        Core.sync(function() set_device_state(source, state) end)
        return
      end
    else
      default_node = 0
    end

    ENABLED_SOURCES[source] = state
    print_volume(source, default_node)
  end

  function enable_devices(devices)
    set_device_state(VolumeSource.INPUT, devices[VolumeSource.INPUT])
    set_device_state(VolumeSource.OUTPUT, devices[VolumeSource.OUTPUT])
  end

  function size(table)
    local count = 0
    for _ in pairs(table) do
      count = count + 1
    end
    return count
  end

  function resync_devices(om)
    devices = { [NodeByInput[VolumeSource.INPUT]] = {}, [NodeByInput[VolumeSource.OUTPUT]] = {} }

    for dev in om:iterate() do
      devices[dev.properties["media.class"]][dev.properties["object.id"]] = true
    end

    enable_devices({
      input = size(devices[NodeByInput[VolumeSource.INPUT]]) >= 1,
      output = size(devices[NodeByInput[VolumeSource.OUTPUT]]) >= 1,
    })
  end

  om = ObjectManager({
    Interest({
      type = "node",
      Constraint({ "media.class", "matches", NodeByInput[VolumeSource.OUTPUT], type = "pw" }),
    }),
    Interest({
      type = "node",
      Constraint({ "media.class", "matches", NodeByInput[VolumeSource.INPUT], type = "pw" }),
    }),
  })

  -- Workaround: Due to some some synchronization issue, wp seems not to pick up the correct
  -- default_node right after some object-added or object-removed has happened. To ensure that we
  -- always get it correctly, let's simply reschedule the callback to run after 100ms after an
  -- event has happened -- either a node is added or removed.
  delayed_resync_devices = function(om)
    resync_devices(om)
    Core.timeout_add(100, function() resync_devices(om); return false end)
  end

  om:connect("object-added", delayed_resync_devices)
  om:connect("object-removed", delayed_resync_devices)
  om:activate()
end)
