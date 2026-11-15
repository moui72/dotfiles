-- Hammerspoon config (symlinked to ~/.hammerspoon/init.lua by mac.setup.sh).

-- Resolve the symlink so this works wherever the dotfiles repo is cloned.
local HERE = hs.fs.pathToAbsolute(hs.configdir .. "/init.lua"):match("(.*)/")

hs.autoLaunch(true)  -- start at login, so the hotkeys below survive a reboot

-- cmd+pgup in Ghostty (fn+cmd+up on a laptop keyboard): fork the focused Claude Code session into a new tab.
-- The hotkey is only enabled while Ghostty is frontmost, so other apps keep cmd+pgup. Overrides Ghostty's default cmd+pgup (scroll_page_up).
local forkTab = hs.hotkey.new({ "cmd" }, "pageup", function()
  hs.task.new(HERE .. "/claude-fork-tab.sh", function(code, _, stderr)
    if code ~= 0 then
      hs.alert.show(((stderr ~= "" and stderr or "claude-fork-tab failed"):gsub("%s+$", "")))
    end
  end):start()
end)

ghosttyWatcher = hs.application.watcher.new(function(name, event)
  if name ~= "Ghostty" then return end
  if event == hs.application.watcher.activated then
    forkTab:enable()
  elseif event == hs.application.watcher.deactivated then
    forkTab:disable()
  end
end)
ghosttyWatcher:start()

local front = hs.application.frontmostApplication()
if front and front:name() == "Ghostty" then forkTab:enable() end
