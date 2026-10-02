--[[
    Copyright © 2026 @APHONlC. All rights reserved.

    No copying, modification, distribution, or sale without prior written permission.
    AI/ML ingestion and training are strictly prohibited (TDM opt-out).

    See LICENSE.md for full terms and maintenance exceptions.
]]

APHCR = {}
local APHCR = APHCR
APHCR.name = "APH-CodeRunner"
APHCR.sessions = {}

local REAL_WINDOW_MANAGER = WINDOW_MANAGER
local REAL_EVENT_MANAGER = EVENT_MANAGER
local SV_CHUNK_BYTES = 1900
local ROW_HEIGHT = 22
local HOOK_NAMES = { "ZO_PreHook", "ZO_PostHook", "SecurePostHook", "ZO_PreHookHandler", "ZO_PostHookHandler" }

local sv
local files = {}
local selected = 1
local known_toplevels = {}
local known_count = 0
local retired = {}
local session_counter = 0
local call_depth = 0

local function ChatLine(message)
	if sv and sv.chat_logs == false then return false end
	d("|cFF4444[CodeRunner]|r " .. message)
	return true
end

local function SplitText(text)
	local chunks, start, len = {}, 1, #text
	while start <= len do
		local stop = math.min(start + SV_CHUNK_BYTES - 1, len)
		while stop < len and stop > start do
			local next_byte = text:byte(stop + 1)
			if next_byte < 128 or next_byte >= 192 then break end
			stop = stop - 1
		end
		chunks[#chunks + 1] = text:sub(start, stop)
		start = stop + 1
	end
	return chunks
end

local function PersistFile(index)
	local file = files[index]
	if not sv or not file then return end
	sv.files[index] = { title = file.title, enabled = file.enabled, chunks = SplitText(file.text) }
end

local function PersistAll()
	if not sv then return end
	sv.files = {}
	for index in ipairs(files) do PersistFile(index) end
end

local function LoadFiles()
	files = {}
	for index, entry in ipairs(sv.files) do
		files[index] = {
			title = entry.title or ("file" .. index .. ".lua"),
			enabled = entry.enabled ~= false,
			text = table.concat(entry.chunks or {}),
		}
	end
	if #files == 0 then files[1] = { title = "main.lua", enabled = true, text = "" } end
end

local function RefreshKnown(owner)
	local count = GuiRoot:GetNumChildren()
	for index = 1, count do
		local child = GuiRoot:GetChild(index)
		if child and not known_toplevels[child] then
			known_toplevels[child] = true
			if owner then owner.toplevels[#owner.toplevels + 1] = child end
		end
	end
	known_count = count
end

APHCR.error_log = {}
local ERROR_LOG_MAX = 200
APHCR.edit_limit = 29903
local error_index = {}
local on_error_logged

local function LogError(run_id, message, location)
	local key = run_id .. "\0" .. message
	local entry = error_index[key]
	local is_new = entry == nil
	if entry then
		entry.count = entry.count + 1
		entry.time = GetTimeString()
	else
		entry = { key = key, run = run_id, message = message, count = 1, time = GetTimeString(), location = location }
		error_index[key] = entry
		APHCR.error_log[#APHCR.error_log + 1] = entry
		if #APHCR.error_log > ERROR_LOG_MAX then
			error_index[table.remove(APHCR.error_log, 1).key] = nil
		end
	end
	if on_error_logged then on_error_logged() end
	return is_new
end

function APHCR.ClearErrors()
	APHCR.error_log = {}
	error_index = {}
	if on_error_logged then on_error_logged() end
end

local function EscapePattern(text)
	return (text:gsub("%W", "%%%0"))
end

local function FindLocation(session, message)
	if not session.groups then return nil end
	local best_position, best_group, best_line
	for _, group in ipairs(session.groups) do
		local position, _, line = message:find(EscapePattern(group.title) .. ":(%d+):")
		if position and (not best_position or position < best_position) then
			best_position, best_group, best_line = position, group, tonumber(line)
		end
	end
	if not best_group then return nil end
	for _, part in ipairs(best_group.parts) do
		if best_line >= part.first and best_line < part.first + part.lines then
			return { index = part.index, line = best_line - part.first + 1, title = best_group.title }
		end
	end
	return nil
end

local function ReportLocated(session, message)
	local location = FindLocation(session, message)
	if location then
		session.first_location = session.first_location or location
		local file = session.file_list and session.file_list[location.index]
		if file then
			file.error_lines = file.error_lines or {}
			file.error_lines[location.line] = true
		end
	end
	LogError(session.id, message, location)
end

local function Finish(session, ok, ...)
	call_depth = call_depth - 1
	if call_depth == 0 then
		rawset(_G, "WINDOW_MANAGER", REAL_WINDOW_MANAGER)
		if GuiRoot:GetNumChildren() ~= known_count then RefreshKnown(session) end
	end
	if not ok then
		ReportLocated(session, tostring((...)))
		error((...), 0)
	end
	return ...
end

local function Guarded(session, fn)
	if type(fn) ~= "function" then return fn end
	return function(...)
		if not session.alive then return end
		if call_depth == 0 then
			if GuiRoot:GetNumChildren() ~= known_count then RefreshKnown(nil) end
			rawset(_G, "WINDOW_MANAGER", session.window_proxy)
		end
		call_depth = call_depth + 1
		return Finish(session, pcall(fn, ...))
	end
end

local function PassThrough(real, proxy)
	return setmetatable(proxy, {
		__index = function(_, key)
			local value = real[key]
			if type(value) ~= "function" then return value end
			return function(self, ...)
				if self == proxy then self = real end
				return value(self, ...)
			end
		end,
	})
end

local function Reuse(session, name, parent)
	if type(name) ~= "string" or name == "" then return nil end
	local existing = GetControl(name)
	if not existing then return nil end
	local owner = existing:GetOwningWindow() or existing
	if not (retired[owner] or session.reclaimed[owner]) then return nil end
	if retired[owner] then
		retired[owner] = nil
		session.reclaimed[owner] = true
		session.toplevels[#session.toplevels + 1] = owner
	end
	if parent and existing:GetParent() ~= parent then existing:SetParent(parent) end
	existing:ClearAnchors()
	existing:SetHidden(false)
	return existing
end

local function MakeWindowProxy(session)
	local proxy = {}
	function proxy:CreateControl(name, parent, control_type)
		return Reuse(session, name, parent) or REAL_WINDOW_MANAGER:CreateControl(name, parent, control_type)
	end
	function proxy:CreateControlFromVirtual(name, parent, template, suffix)
		local full_name = name and (name .. (suffix or "")) or nil
		return Reuse(session, full_name, parent) or REAL_WINDOW_MANAGER:CreateControlFromVirtual(name, parent, template, suffix)
	end
	function proxy:CreateTopLevelWindow(name)
		return Reuse(session, name, GuiRoot) or REAL_WINDOW_MANAGER:CreateTopLevelWindow(name)
	end
	return PassThrough(REAL_WINDOW_MANAGER, proxy)
end

local function MakeEventProxy(session)
	local prefix = "APHCR" .. session.id .. "_"
	local function Scoped(name) return prefix .. tostring(name) end
	local proxy = {}
	function proxy:RegisterForEvent(name, event, fn, do_once)
		local guarded = Guarded(session, fn)
		session.events[Scoped(name) .. "\0" .. tostring(event)] = { Scoped(name), event }
		if event == EVENT_ADD_ON_LOADED then session.loaded[name] = guarded end
		if event == EVENT_PLAYER_ACTIVATED then session.activated[name] = guarded end
		return REAL_EVENT_MANAGER:RegisterForEvent(Scoped(name), event, guarded, do_once)
	end
	function proxy:UnregisterForEvent(name, event)
		session.events[Scoped(name) .. "\0" .. tostring(event)] = nil
		if event == EVENT_ADD_ON_LOADED then session.loaded[name] = nil end
		if event == EVENT_PLAYER_ACTIVATED then session.activated[name] = nil end
		return REAL_EVENT_MANAGER:UnregisterForEvent(Scoped(name), event)
	end
	function proxy:AddFilterForEvent(name, event, ...)
		return REAL_EVENT_MANAGER:AddFilterForEvent(Scoped(name), event, ...)
	end
	function proxy:RegisterForAllEvents(name, fn)
		session.all_events[Scoped(name)] = true
		return REAL_EVENT_MANAGER:RegisterForAllEvents(Scoped(name), Guarded(session, fn))
	end
	function proxy:UnregisterForAllEvents(name)
		session.all_events[Scoped(name)] = nil
		session.loaded[name], session.activated[name] = nil, nil
		return REAL_EVENT_MANAGER:UnregisterForAllEvents(Scoped(name))
	end
	function proxy:RegisterForUpdate(name, interval, fn, do_once)
		session.updates[Scoped(name)] = true
		return REAL_EVENT_MANAGER:RegisterForUpdate(Scoped(name), interval, Guarded(session, fn), do_once)
	end
	function proxy:UnregisterForUpdate(name)
		session.updates[Scoped(name)] = nil
		return REAL_EVENT_MANAGER:UnregisterForUpdate(Scoped(name))
	end
	function proxy:RegisterForPostEffectsUpdate(name, interval, fn, do_once)
		session.post_updates[Scoped(name)] = true
		return REAL_EVENT_MANAGER:RegisterForPostEffectsUpdate(Scoped(name), interval, Guarded(session, fn), do_once)
	end
	function proxy:UnregisterForPostEffectsUpdate(name)
		session.post_updates[Scoped(name)] = nil
		return REAL_EVENT_MANAGER:UnregisterForPostEffectsUpdate(Scoped(name))
	end
	return PassThrough(REAL_EVENT_MANAGER, proxy)
end

local function MakeCallbackProxy(session, real)
	local proxy = {}
	local guarded_by_fn = {}
	function proxy:RegisterCallback(name, fn, ...)
		local guarded = Guarded(session, fn)
		guarded_by_fn[fn] = guarded
		session.callbacks[#session.callbacks + 1] = { real, name, guarded }
		return real:RegisterCallback(name, guarded, ...)
	end
	function proxy:UnregisterCallback(name, fn)
		return real:UnregisterCallback(name, guarded_by_fn[fn] or fn)
	end
	return PassThrough(real, proxy)
end

local function MakeSlashProxy(session)
	return setmetatable({}, {
		__index = SLASH_COMMANDS,
		__newindex = function(_, key, value)
			if not session.slash[key] then session.slash[key] = { prev = SLASH_COMMANDS[key] } end
			SLASH_COMMANDS[key] = Guarded(session, value)
		end,
	})
end

local function MakeSavedVarsSandbox(session, env)
	local function Sandbox(name)
		local sandbox = session.saved[name]
		if not sandbox then
			sandbox = {}
			session.saved[name] = sandbox
			rawset(env, name, sandbox)
		end
		return sandbox
	end
	local proxy
	proxy = setmetatable({}, {
		__index = function(_, key)
			local value = ZO_SavedVars[key]
			if type(value) ~= "function" then return value end
			return function(self, first, ...)
				if self == proxy then self = ZO_SavedVars end
				if type(first) == "string" then first = Sandbox(first) end
				return value(self, first, ...)
			end
		end,
	})
	rawset(env, "ZO_SavedVars", proxy)
	return Sandbox
end

local function MakeEnv(session, saved_names)
	local env = {}
	setmetatable(env, {
		__index = function(_, key) return _G[key] end,
		__newindex = function(_, key, value) rawset(env, key, value) end,
	})
	local Sandbox = MakeSavedVarsSandbox(session, env)
	for name in (saved_names or ""):gmatch("[%w_]+") do Sandbox(name) end
	local event_proxy = MakeEventProxy(session)
	rawset(env, "_G", env)
	rawset(env, "getfenv", function(level)
		if level == nil or level == 0 then return env end
		if type(level) == "number" then level = level + 1 end
		return getfenv(level)
	end)
	rawset(env, "setfenv", function(level, table_env)
		if level == 0 then error("setfenv(0) would swap the game's globals; a run keeps its own", 2) end
		if type(level) == "number" then level = level + 1 end
		return setfenv(level, table_env)
	end)
	rawset(env, "EVENT_MANAGER", event_proxy)
	rawset(env, "GetEventManager", function() return event_proxy end)
	rawset(env, "WINDOW_MANAGER", session.window_proxy)
	rawset(env, "GetWindowManager", function() return session.window_proxy end)
	rawset(env, "SLASH_COMMANDS", MakeSlashProxy(session))
	rawset(env, "CALLBACK_MANAGER", MakeCallbackProxy(session, CALLBACK_MANAGER))
	rawset(env, "SCENE_MANAGER", MakeCallbackProxy(session, SCENE_MANAGER))
	rawset(env, "zo_callLater", function(fn, delay_ms)
		local id
		id = zo_callLater(function()
			session.later[id] = nil
			Guarded(session, fn)()
		end, delay_ms)
		session.later[id] = true
		return id
	end)
	for _, hook_name in ipairs(HOOK_NAMES) do
		local real_hook = _G[hook_name]
		if real_hook then
			rawset(env, hook_name, function(first, second, third, ...)
				if type(second) == "function" then return real_hook(first, Guarded(session, second)) end
				return real_hook(first, second, Guarded(session, third), ...)
			end)
		end
	end
	return env
end

local function NewSession(addon_name)
	session_counter = session_counter + 1
	local session = {
		id = session_counter, alive = true, addon_name = addon_name,
		events = {}, all_events = {}, updates = {}, post_updates = {}, later = {}, slash = {}, saved = {}, callbacks = {},
		toplevels = {}, reclaimed = {}, stops = {}, loaded = {}, activated = {},
	}
	session.window_proxy = MakeWindowProxy(session)
	return session
end

local function FireTracked(handlers, event_code, arg, errors)
	local snapshot = {}
	for namespace, fn in pairs(handlers) do snapshot[#snapshot + 1] = { namespace, fn } end
	for _, entry in ipairs(snapshot) do
		local ok, err = pcall(entry[2], event_code, arg)
		if not ok then errors[#errors + 1] = entry[1] .. ": " .. tostring(err) end
	end
end

function APHCR.RunFiles(file_list, addon_name, saved_names)
	if not (AreUserAddOnsSupported() or IsInternalBuild()) then
		return false, "User add-ons are not supported in this client/account state."
	end
	local session = NewSession(addon_name ~= "" and addon_name or ("APHCodeRunnerRun" .. session_counter + 1))
	local env = MakeEnv(session, saved_names)
	local errors, ran = {}, 0
	RefreshKnown(nil)
	APHCR.sessions[#APHCR.sessions + 1] = session

	local runnable = {}
	session.file_list = file_list
	for _, file in ipairs(file_list) do file.error_lines = nil end
	for index, file in ipairs(file_list) do
		if file.enabled ~= false and not file.text:match("^%s*$") then
			local _, newlines = file.text:gsub("\n", "")
			local last = runnable[#runnable]
			local part
			if last and last.title == file.title then
				part = { index = index, first = last.next_line, lines = newlines + 1 }
				last.text = last.text .. "\n" .. file.text
				last.parts[#last.parts + 1] = part
				last.longest = math.max(last.longest, #file.text)
			else
				part = { index = index, first = 1, lines = newlines + 1 }
				last = { title = file.title, text = file.text, parts = { part }, longest = #file.text }
				runnable[#runnable + 1] = last
			end
			last.next_line = part.first + part.lines
		end
	end
	session.groups = runnable

	for _, file in ipairs(runnable) do
		do
			local chunk, compile_err = zo_loadstring(file.text, "@" .. file.title)
			if not chunk then
				local message = file.title .. ": " .. tostring(compile_err)
				if tostring(compile_err):find("<eof>", 1, true) and file.longest >= APHCR.edit_limit - 2500 then
					message = message .. string.format(" - this box holds %d characters and ESO's edit boxes stop at %d (a line break counts as 2). Split the file into two boxes with the same name.", file.longest, APHCR.edit_limit)
				end
				errors[#errors + 1] = message
				ReportLocated(session, message)
			else
				setfenv(chunk, env)
				local ok, result = pcall(Guarded(session, chunk))
				ran = ran + 1
				if not ok then
					errors[#errors + 1] = file.title .. ": " .. tostring(result)
				elseif type(result) == "function" then
					session.stops[#session.stops + 1] = result
				end
			end
		end
	end

	FireTracked(session.loaded, EVENT_ADD_ON_LOADED, session.addon_name, errors)
	FireTracked(session.activated, EVENT_PLAYER_ACTIVATED, true, errors)

	for _, message in ipairs(errors) do ChatLine(message) end
	if #errors > 0 then
		return false, string.format("Run %d: %d file(s), %d error(s) - see Errors.", session.id, ran, #errors), session.first_location
	end
	return true, string.format("Run %d: %d file(s) loaded as %s.", session.id, ran, session.addon_name)
end

local function RemoveFragmentsFor(owned)
	for _, scene in pairs(SCENE_MANAGER.scenes or {}) do
		local fragments = scene.fragments
		if fragments then
			for index = #fragments, 1, -1 do
				local control = fragments[index].control
				if control and owned[control:GetOwningWindow() or control] then
					scene:RemoveFragment(fragments[index])
				end
			end
		end
	end
end

local function StopSession(session)
	if not session.alive then return false end
	session.alive = false
	for _, fn in ipairs(session.stops) do pcall(fn) end
	for _, entry in pairs(session.events) do REAL_EVENT_MANAGER:UnregisterForEvent(entry[1], entry[2]) end
	for namespace in pairs(session.all_events) do REAL_EVENT_MANAGER:UnregisterForAllEvents(namespace) end
	for namespace in pairs(session.updates) do REAL_EVENT_MANAGER:UnregisterForUpdate(namespace) end
	for namespace in pairs(session.post_updates) do REAL_EVENT_MANAGER:UnregisterForPostEffectsUpdate(namespace) end
	for id in pairs(session.later) do zo_removeCallLater(id) end
	for _, entry in ipairs(session.callbacks) do entry[1]:UnregisterCallback(entry[2], entry[3]) end
	for key, entry in pairs(session.slash) do SLASH_COMMANDS[key] = entry.prev end
	local owned = {}
	for _, control in ipairs(session.toplevels) do
		owned[control] = true
		retired[control] = true
		control:SetHidden(true)
	end
	RemoveFragmentsFor(owned)
	session.saved = {}
	return true
end

function APHCR.StopLast()
	for index = #APHCR.sessions, 1, -1 do
		local session = table.remove(APHCR.sessions, index)
		if StopSession(session) then return true, string.format("Stopped run %d.", session.id) end
	end
	return false, "Nothing is running."
end

function APHCR.StopAll()
	local count = 0
	for index = #APHCR.sessions, 1, -1 do
		if StopSession(APHCR.sessions[index]) then count = count + 1 end
		APHCR.sessions[index] = nil
	end
	return count
end

local win, list_rows, title_box, addon_box, saved_box, status_lbl, chars_lbl, errors_btn, list_bar
local editor, viewer_view, errors_view
local menu_fragment
local wanted_open = false
local row_pool = {}
local list_offset = 0
local views = {}
local search_box, search_status
local reset_code_search
local LeaveUIModeIfIdle

local WHEEL_STEP = 48
local SCROLLBAR_SPACE = 18
local BAR_HIT_WIDTH = 16
local GUTTER_WIDTH = 48
local RELAYOUT_DELAY_MS = 120
local HUGE_INPUT_CHARS = 10000000
local FONT_SIZES = { 10, 11, 12, 13, 14, 16, 18, 20 }
local CLOSED_REASON = "APHCodeRunnerClosed"
local SEARCH_HIGHLIGHT = { 1, 0.5, 0.05, 0.55 }

local function Font(size)
	return string.format("$(MEDIUM_FONT)|%d|soft-shadow-thin", size or 14)
end

local function EditorFont()
	return Font(sv.font_size)
end

local function ReportInternal(label, err)
	local message = label .. ": " .. tostring(err)
	if LogError(0, message) then ChatLine(message) end
end

local function Safe(label, fn)
	return function(...)
		local ok, first, second = pcall(fn, ...)
		if not ok then
			ReportInternal(label, first)
			return
		end
		return first, second
	end
end

local function On(control, event, fn, label)
	control:SetHandler(event, Safe(label or event, fn))
end

local function Every(name, ms, fn)
	EVENT_MANAGER:RegisterForUpdate(name, ms, Safe(name, fn))
end

local function SplitLines(text)
	local lines, count, from = {}, 0, 1
	while true do
		local stop = text:find("\n", from, true)
		count = count + 1
		lines[count] = text:sub(from, stop and (stop - 1) or nil)
		if not stop then break end
		from = stop + 1
	end
	return lines
end

local function SetStatus(ok, message)
	status_lbl:SetColor(ok and 0.4 or 1, ok and 1 or 0.3, 0.4, 1)
	status_lbl:SetText(message)
end

local function RefreshList()
	local max_offset = math.max(#files - #list_rows, 0)
	list_offset = zo_clamp(list_offset, 0, max_offset)
	for row_index, row in ipairs(list_rows) do
		local file_index = row_index + list_offset
		local file = files[file_index]
		row.file_index = file_index
		row:SetHidden(file == nil)
		if file then
			local enabled = file.enabled ~= false
			ZO_CheckButton_SetCheckState(row.check, enabled)
			row.label:SetText(string.format("%d. %s", file_index, file.title))
			local color = LibAPH.THEME.TEXT
			if file_index == selected then color = LibAPH.THEME.ACCENT elseif not enabled then color = LibAPH.THEME.MUTED end
			row.label:SetColor(unpack(color))
		end
	end
	if list_bar then list_bar:Update(list_offset, max_offset, #list_rows / math.max(#files, 1)) end
end

local function RefreshCharCount()
	local count = #(files[selected] and files[selected].text or "")
	local limit = editor and editor.max_chars or APHCR.edit_limit
	chars_lbl:SetText(string.format("%d / %d", count, limit))
	chars_lbl:SetColor(unpack(count >= limit - 1500 and { 1, 0.35, 0.35, 1 } or LibAPH.THEME.MUTED))
end

local function MakeButton(name, parent, text, width, onClick)
	local button = WINDOW_MANAGER:CreateControlFromVirtual(name, parent, "ZO_DefaultButton")
	button:SetDimensions(width, 26)
	button:SetText(text)
	On(button, "OnClicked", onClick, name)
	return button
end

local function MakeLabel(parent, text, size, color, name)
	local label = WINDOW_MANAGER:CreateControl(name, parent, CT_LABEL)
	label:SetFont(Font(size))
	label:SetColor(unpack(color or LibAPH.THEME.TEXT))
	label:SetText(text)
	return label
end

local function MakeLineEdit(name, parent, ghost, on_changed)
	local backdrop = WINDOW_MANAGER:CreateControlFromVirtual(name .. "BG", parent, "ZO_EditBackdrop")
	backdrop:SetHeight(26)
	local edit = WINDOW_MANAGER:CreateControlFromVirtual(name, backdrop, "ZO_DefaultEditForBackdrop")
	edit:SetFont(Font(13))
	On(edit, "OnTextChanged", on_changed, name)
	LibAPH.AddGhostText(edit, ghost)
	return backdrop, edit
end

local function MakeCombo(name, parent, width, items, selected_index, on_select)
	local container = WINDOW_MANAGER:CreateControlFromVirtual(name, parent, "ZO_ComboBox")
	container:SetDimensions(width, 24)
	local combo = ZO_ComboBox_ObjectFromContainer(container)
	combo:SetSortsItems(false)
	for index, text in ipairs(items) do
		combo:AddItem(combo:CreateItemEntry(text, Safe(name, function() on_select(index) end)))
	end
	combo:SelectItemByIndex(selected_index, true)
	LibAPH.UseGreenSelection(combo)
	return container, combo
end

local function MakeScrollbar(parent, name, anchor_to, opts)
	local THEME = LibAPH.THEME
	local bar = { position = 0, range = 0, fraction = 1, thumb_height = 0, height = 0 }
	local inset = (BAR_HIT_WIDTH - THEME.SCROLLBAR_W) / 2
	local drag_event = "APHCodeRunnerDrag" .. name

	local hit = WINDOW_MANAGER:CreateControl(name .. "Bar", parent, CT_CONTROL)
	hit:SetWidth(BAR_HIT_WIDTH)
	if opts.inside then
		hit:SetAnchor(TOPRIGHT, anchor_to, TOPRIGHT, -2, 4)
		hit:SetAnchor(BOTTOMRIGHT, anchor_to, BOTTOMRIGHT, -2, -4)
	else
		hit:SetAnchor(TOPLEFT, anchor_to, TOPRIGHT, 2, 0)
		hit:SetAnchor(BOTTOMLEFT, anchor_to, BOTTOMRIGHT, 2, 0)
	end
	hit:SetMouseEnabled(true)
	hit:SetHidden(true)

	local track = WINDOW_MANAGER:CreateControl(name .. "Track", hit, CT_TEXTURE)
	track:SetColor(unpack(THEME.TRACK))
	track:SetWidth(THEME.SCROLLBAR_W)
	track:SetAnchor(TOPRIGHT, hit, TOPRIGHT, -inset, 0)
	track:SetAnchor(BOTTOMRIGHT, hit, BOTTOMRIGHT, -inset, 0)
	local thumb = WINDOW_MANAGER:CreateControl(name .. "Thumb", hit, CT_TEXTURE)
	thumb:SetColor(unpack(THEME.THUMB))
	thumb:SetDrawLevel(2)

	function bar:Update(position, range, fraction)
		self.position, self.range, self.fraction = position, range, fraction
		local height = hit:GetHeight()
		local shown = range > 0 and height > 0
		hit:SetHidden(not shown)
		if not shown then return end
		local thumb_height = zo_clamp(height * fraction, THEME.MIN_THUMB_H, height)
		self.thumb_height, self.height = thumb_height, height
		thumb:SetDimensions(THEME.SCROLLBAR_W, thumb_height)
		thumb:ClearAnchors()
		thumb:SetAnchor(TOPRIGHT, hit, TOPRIGHT, -inset, (height - thumb_height) * (position / range))
	end

	local locked_window
	local function StopDrag()
		hit:SetHandler("OnUpdate", nil)
		EVENT_MANAGER:UnregisterForEvent(drag_event, EVENT_GLOBAL_MOUSE_UP)
		if locked_window then
			locked_window:SetMovable(true)
			locked_window = nil
		end
	end

	On(hit, "OnMouseDown", function(_, button)
		if button ~= MOUSE_BUTTON_INDEX_LEFT or bar.range <= 0 then return end
		local _, y = GetUIMousePosition()
		local thumb_top = hit:GetTop() + (bar.height - bar.thumb_height) * (bar.position / bar.range)
		if y >= thumb_top and y <= thumb_top + bar.thumb_height then
			local start_y, start_position = y, bar.position
			locked_window = hit:GetOwningWindow()
			if locked_window then locked_window:SetMovable(false) end
			EVENT_MANAGER:RegisterForEvent(drag_event, EVENT_GLOBAL_MOUSE_UP, Safe(name .. " release", StopDrag))
			hit:SetHandler("OnUpdate", Safe(name .. " drag", function()
				local _, now_y = GetUIMousePosition()
				local travel = bar.height - bar.thumb_height
				if travel > 0 then opts.set_position(start_position + (now_y - start_y) / travel * bar.range) end
			end))
		elseif y < thumb_top then
			opts.set_position(bar.position - opts.page())
		else
			opts.set_position(bar.position + opts.page())
		end
	end, name .. " bar down")
	On(hit, "OnMouseUp", StopDrag, name .. " bar up")
	On(hit, "OnMouseWheel", function(_, delta) opts.set_position(bar.position - delta * opts.wheel_step) end, name .. " bar wheel")
	bar.hit = hit
	return bar
end

local function MakeScrollText(parent, name, opts)
	opts = opts or {}
	local THEME = LibAPH.THEME
	local gutter_width = opts.gutter and GUTTER_WIDTH or 0
	local view = {
		offset = 0, content_height = 0, pitch = 16, text_width = 400,
		loading = false, line_visual = {}, line_rows = {}, max_chars = APHCR.edit_limit,
	}
	views[#views + 1] = view

	local area = WINDOW_MANAGER:CreateControl(name .. "Area", parent, CT_CONTROL)
	LibAPH.ApplyPanelBackdrop(area, name .. "AreaBG", THEME.INSET)

	local viewport = WINDOW_MANAGER:CreateControl(name .. "View", area, CT_SCROLL)
	viewport:SetAnchor(TOPLEFT, area, TOPLEFT, 8, 8)
	viewport:SetAnchor(BOTTOMRIGHT, area, BOTTOMRIGHT, -8 - SCROLLBAR_SPACE, -8)
	viewport:SetMouseEnabled(true)

	local content = WINDOW_MANAGER:CreateControl(name .. "Content", viewport, CT_CONTROL)
	content:SetHeight(100)
	content:SetAnchor(TOPLEFT, viewport, TOPLEFT, 0, 0)
	content:SetAnchor(TOPRIGHT, viewport, TOPRIGHT, 0, 0)

	local gutter
	if opts.gutter then
		gutter = WINDOW_MANAGER:CreateControl(name .. "Gutter", content, CT_LABEL)
		gutter:SetFont(EditorFont())
		gutter:SetColor(0.52, 0.52, 0.52, 1)
		gutter:SetHorizontalAlignment(TEXT_ALIGN_RIGHT)
		gutter:SetVerticalAlignment(TEXT_ALIGN_TOP)
		gutter:SetMouseEnabled(false)
		gutter:SetWidth(gutter_width - 10)
		gutter:SetAnchor(TOPLEFT, content, TOPLEFT, 0, 0)
	end

	local box = WINDOW_MANAGER:CreateControlFromVirtual(opts.box_name or (name .. "Text"), content, "ZO_DefaultEditMultiLineForBackdrop")
	box:ClearAnchors()
	box:SetAnchor(TOPLEFT, content, TOPLEFT, gutter_width, 0)
	box:SetAnchor(BOTTOMRIGHT, content, BOTTOMRIGHT, 0, 0)
	box:SetFont(EditorFont())
	box:SetMaxInputChars(HUGE_INPUT_CHARS)
	local reported_limit = box:GetMaxInputChars()
	if type(reported_limit) == "number" and reported_limit > 0 then view.max_chars = reported_limit end
	if opts.gutter then APHCR.edit_limit = view.max_chars end
	box:SetSelectionColor(unpack(SEARCH_HIGHLIGHT))
	if opts.read_only then
		box:SetEditEnabled(false)
		box:SetCopyEnabled(true)
	end

	local measure = WINDOW_MANAGER:CreateControl(nil, parent, CT_LABEL)
	measure:SetAlpha(0)
	measure:SetMouseEnabled(false)
	measure:SetAnchor(TOPLEFT, parent, TOPLEFT, 0, 0)

	view.area, view.box = area, box
	local bar

	function view:Range()
		return math.max(self.content_height - viewport:GetHeight(), 0)
	end

	function view:UpdateScrollbar()
		if not bar then return end
		local viewport_height = viewport:GetHeight()
		local fraction = self.content_height > 0 and (viewport_height / self.content_height) or 1
		bar:Update(self.offset, self:Range(), fraction)
	end

	function view:SetOffset(value)
		self.offset = zo_clamp(value, 0, self:Range())
		content:ClearAnchors()
		content:SetAnchor(TOPLEFT, viewport, TOPLEFT, 0, -self.offset)
		content:SetAnchor(TOPRIGHT, viewport, TOPRIGHT, 0, -self.offset)
		self:UpdateScrollbar()
	end

	local function Wheel(_, delta) view:SetOffset(view.offset - delta * WHEEL_STEP) end
	On(box, "OnMouseWheel", Wheel, name .. " wheel")
	On(viewport, "OnMouseWheel", Wheel, name .. " view wheel")
	bar = MakeScrollbar(area, name, viewport, {
		set_position = function(value) view:SetOffset(value) end,
		page = function() return math.max(viewport:GetHeight() - view.pitch * 2, view.pitch) end,
		wheel_step = WHEEL_STEP,
	})

	function view:UpdateGutter()
		if not gutter then return end
		local marks = opts.marks and opts.marks() or {}
		local numbers = {}
		for line, rows in ipairs(self.line_rows) do
			numbers[#numbers + 1] = marks[line] and ("|cFF5555" .. line .. "|r") or tostring(line)
			for _ = 2, rows do numbers[#numbers + 1] = " " end
		end
		gutter:SetFont(EditorFont())
		gutter:SetText(table.concat(numbers, "\n"))
	end

	function view:ComputeLines(text)
		local lines = SplitLines(text)
		local index = 0
		self.line_visual, self.line_rows = {}, {}
		for line_number, line in ipairs(lines) do
			local rows = 1
			if line ~= "" and measure:GetStringWidth(line) / GetUIGlobalScale() > self.text_width then
				measure:SetText(line)
				rows = math.max(1, math.floor(measure:GetTextHeight() / self.pitch + 0.5))
			end
			self.line_visual[line_number] = index
			self.line_rows[line_number] = rows
			index = index + rows
		end
		self.visual_lines = index
	end

	function view:Relayout()
		local font = EditorFont()
		self.text_width = math.max(50, viewport:GetWidth() - gutter_width)
		measure:SetFont(font)
		measure:SetWidth(self.text_width)
		measure:SetText("Ag")
		self.pitch = math.max(measure:GetTextHeight(), 1)
		local text = box:GetText():gsub("[\r\t]", "")
		measure:SetText(text)
		local wrapped_height = measure:GetTextHeight()
		self:ComputeLines(text)
		self.content_height = math.max(math.max(wrapped_height, self.visual_lines * self.pitch) + self.pitch * 2, viewport:GetHeight())
		content:SetHeight(self.content_height)
		self:UpdateGutter()
		self:SetOffset(self.offset)
	end

	function view:SetText(text, keep_scroll, force)
		if not force and box:GetText() == text then return end
		local previous_offset = self.offset
		self.loading = true
		if self.history then
			self.history:RunSilently(function() box:SetText(text) end)
		else
			box:SetText(text)
		end
		self.loading = false
		self:Relayout()
		self:SetOffset(keep_scroll and previous_offset or 0)
	end

	function view:ApplyFont()
		box:SetFont(EditorFont())
		self:Relayout()
	end

	function view:ScrollToLine(line)
		local visual = self.line_visual[line] or (line - 1)
		self:SetOffset(math.max(0, (visual - 3) * self.pitch))
	end

	function view:ReplaceText(text, cursor)
		self.loading = true
		box:SetText(text)
		self.loading = false
		box:SetCursorPosition(cursor)
		if opts.on_change then opts.on_change(text) end
		self:OnEdited()
	end

	function view:HighlightLine(line)
		local text = box:GetText()
		local start, current = 1, 1
		while current < line do
			local newline = text:find("\n", start, true)
			if not newline then break end
			start = newline + 1
			current = current + 1
		end
		local stop = (text:find("\n", start, true) or (#text + 1)) - 1
		if text:sub(stop, stop) == "\r" then stop = stop - 1 end
		box:SetCursorPosition(start - 1)
		box:SetSelection(start - 1, math.max(stop, start - 1))
		self:ScrollToLine(line)
	end

	function view:KeepCursorVisible()
		local cursor = box:GetCursorPosition()
		local before = box:GetText():sub(1, cursor):gsub("[\r\t]", "")
		measure:SetFont(EditorFont())
		measure:SetWidth(self.text_width)
		measure:SetText(before .. "x")
		local caret_top = measure:GetTextHeight() - self.pitch
		local viewport_height = viewport:GetHeight()
		if caret_top < self.offset then
			self:SetOffset(caret_top)
		elseif caret_top + self.pitch * 2 > self.offset + viewport_height then
			self:SetOffset(caret_top + self.pitch * 2 - viewport_height)
		end
	end

	local relayout_timer = name .. "Relayout"
	function view:OnEdited()
		Every(relayout_timer, RELAYOUT_DELAY_MS, function()
			EVENT_MANAGER:UnregisterForUpdate(relayout_timer)
			self:Relayout()
			if opts.follow_cursor then self:KeepCursorVisible() end
			if opts.after_edit then opts.after_edit(self) end
		end)
	end

	On(box, "OnTextChanged", function(self)
		if view.loading then return end
		if opts.on_change then opts.on_change(self:GetText()) end
		view:OnEdited()
	end, name .. " text changed")
	On(viewport, "OnRectChanged", function() view:Relayout() end, name .. " resize")
	if opts.undo then view.history = LibAPH.EnableUndoRedo(box) end
	return view
end

local function AttachSearch(input, status, target, scroll_to_line)
	local search_pos = 1
	local function Search(forward)
		local needle = input:GetText():lower()
		if needle == "" then
			status:SetText("")
			return
		end
		local haystack = target:GetText():lower()
		local total, index_of, pos = 0, {}, 1
		while true do
			local found = haystack:find(needle, pos, true)
			if not found then break end
			total = total + 1
			index_of[found] = total
			pos = found + 1
		end
		if total == 0 then
			status:SetColor(1, 0.4, 0.4, 1)
			status:SetText("No matches")
			return
		end
		local match_start, match_end
		if forward then
			match_start, match_end = haystack:find(needle, search_pos, true)
			if not match_start then match_start, match_end = haystack:find(needle, 1, true) end
		else
			pos = 1
			local wrap_start, wrap_end
			while true do
				local found, found_end = haystack:find(needle, pos, true)
				if not found then break end
				if found < search_pos then match_start, match_end = found, found_end end
				wrap_start, wrap_end = found, found_end
				pos = found + 1
			end
			if not match_start then match_start, match_end = wrap_start, wrap_end end
		end
		target:SetCursorPosition(match_start - 1)
		target:SetSelection(match_start - 1, match_end)
		local _, newlines = haystack:sub(1, match_start):gsub("\n", "")
		scroll_to_line(newlines + 1)
		search_pos = forward and (match_end + 1) or match_start
		status:SetColor(0.6, 1, 0.6, 1)
		status:SetText(string.format("%d/%d", index_of[match_start], total))
	end
	On(input, "OnEnter", function() Search(not IsShiftKeyDown()) end, "search enter")
	On(input, "OnUpArrow", function() Search(false) end, "search up")
	On(input, "OnDownArrow", function() Search(true) end, "search down")
	return function()
		search_pos = 1
		status:SetText("")
	end
end

local history_owner

local function SelectFile(index)
	if history_owner then history_owner.undo_state = editor.history:TakeState() end
	selected = zo_clamp(index, 1, #files)
	title_box:SetText(files[selected].title)
	editor:SetText(files[selected].text, false, true)
	editor.history:SetState(files[selected].undo_state)
	history_owner = files[selected]
	reset_code_search()
	RefreshCharCount()
	RefreshList()
end

local VIEWER_MAX_DEPTH = 10
local VIEWER_REFRESH_MS = 1000
local viewer, viewer_status

local function LatestLiveSession()
	for index = #APHCR.sessions, 1, -1 do
		if APHCR.sessions[index].alive then return APHCR.sessions[index] end
	end
	return nil
end

local function SortedKeys(tbl)
	local keys = {}
	for key in pairs(tbl) do keys[#keys + 1] = key end
	table.sort(keys, function(a, b)
		if type(a) == type(b) and (type(a) == "number" or type(a) == "string") then return a < b end
		return tostring(a) < tostring(b)
	end)
	return keys
end

local function FormatValue(value)
	if type(value) == "string" then
		if #value > 200 then value = value:sub(1, 200) .. "..." end
		return string.format("%q", value)
	end
	return tostring(value)
end

local function DumpTable(lines, budget, tbl, indent, depth, seen)
	for _, key in ipairs(SortedKeys(tbl)) do
		if budget.cut then return end
		local value = tbl[key]
		local label = indent .. "[" .. FormatValue(key) .. "] = "
		local function Add(line)
			budget.used = budget.used + #line + 2
			if budget.used > budget.limit then
				budget.cut = true
				return false
			end
			lines[#lines + 1] = line
			return true
		end
		if type(value) == "table" then
			if seen[value] then
				Add(label .. "{...} (already shown)")
			elseif depth >= VIEWER_MAX_DEPTH then
				Add(label .. "{...} (too deep)")
			elseif Add(label .. "{") then
				seen[value] = true
				DumpTable(lines, budget, value, indent .. "    ", depth + 1, seen)
				if not budget.cut then Add(indent .. "}") end
			end
		else
			Add(label .. FormatValue(value))
		end
	end
end

local function BuildViewerText(limit)
	local session = LatestLiveSession()
	if not session then return "No run is active.", "Run All first; its sandboxed SavedVariables show here." end
	local roots = {}
	for _, key in ipairs(SortedKeys(session.saved)) do roots[#roots + 1] = { key, session.saved[key] } end
	if #roots == 0 then return "This run has no SavedVariables yet.", string.format("Run %d sandbox", session.id) end
	local lines = {}
	local budget = { used = 0, limit = limit - 200, cut = false }
	for _, root in ipairs(roots) do
		if budget.cut then break end
		if type(root[2]) == "table" then
			lines[#lines + 1] = root[1] .. " = {"
			DumpTable(lines, budget, root[2], "    ", 1, { [root[2]] = true })
			if not budget.cut then lines[#lines + 1] = "}" end
		else
			lines[#lines + 1] = root[1] .. " = " .. FormatValue(root[2])
		end
	end
	if budget.cut then
		lines[#lines + 1] = string.format("... cut here: ESO edit boxes hold at most %d characters", limit)
	end
	return table.concat(lines, "\n"), string.format("Run %d sandbox", session.id)
end

local function RefreshViewer()
	local text, source = BuildViewerText(viewer_view.max_chars)
	viewer_status:SetText(source .. " - updates every second")
	viewer_view:SetText(text, true)
end

local function MakeTextWindow(name, title)
	local window = WINDOW_MANAGER:CreateTopLevelWindow(name)
	window:SetDimensions(480, 540)
	window:SetClampedToScreen(true)
	window:SetMouseEnabled(true)
	window:SetMovable(true)
	window:SetDrawTier(DT_MEDIUM)
	window:SetDrawLayer(DL_OVERLAY)
	window:SetDrawLevel(9100)
	window:SetHidden(true)
	LibAPH.ApplyPanelBackdrop(window, name .. "BG", LibAPH.THEME.BG)
	LibAPH.CreateHeaderStrip(window, name .. "Header", 30)
	LibAPH.CreateThemedCloseButton(window, name .. "Close", function()
		window:SetHidden(true)
		LeaveUIModeIfIdle()
	end, 12, 10)
	LibAPH.MakeWindowResizable(window, { minWidth = 320, minHeight = 260 })
	MakeLabel(window, title, 16):SetAnchor(TOPLEFT, window, TOPLEFT, 12, 8)

	local status = MakeLabel(window, "", 13, LibAPH.THEME.MUTED)
	status:SetAnchor(BOTTOMLEFT, window, BOTTOMLEFT, 12, -10)
	status:SetAnchor(BOTTOMRIGHT, window, BOTTOMRIGHT, -12, -10)
	return window, status
end

local function BuildViewer()
	viewer, viewer_status = MakeTextWindow("APHCodeRunnerViewer", "SavedVariables Viewer")

	local reset_viewer_search
	local search_bg, viewer_search = MakeLineEdit("APHCodeRunnerViewerSearch", viewer, "Search saved variables - Enter next, Shift+Enter previous", function()
		if reset_viewer_search then reset_viewer_search() end
	end)
	search_bg:SetAnchor(TOPLEFT, viewer, TOPLEFT, 12, 40)
	search_bg:SetAnchor(TOPRIGHT, viewer, TOPRIGHT, -70, 40)
	local viewer_search_status = MakeLabel(viewer, "", 13, LibAPH.THEME.MUTED)
	viewer_search_status:SetAnchor(LEFT, search_bg, RIGHT, 8, 0)

	viewer_view = MakeScrollText(viewer, "APHCodeRunnerViewer", { read_only = true })
	viewer_view.area:SetAnchor(TOPLEFT, search_bg, BOTTOMLEFT, 0, 8)
	viewer_view.area:SetAnchor(BOTTOMRIGHT, viewer_status, TOPRIGHT, 0, -8)
	reset_viewer_search = AttachSearch(viewer_search, viewer_search_status, viewer_view.box, function(line)
		viewer_view:ScrollToLine(line)
	end)

	On(viewer, "OnShow", function()
		viewer_view:Relayout()
		RefreshViewer()
		Every("APHCodeRunnerViewer", VIEWER_REFRESH_MS, RefreshViewer)
	end, "viewer show")
	On(viewer, "OnHide", function()
		EVENT_MANAGER:UnregisterForUpdate("APHCodeRunnerViewer")
	end, "viewer hide")
end

local errors_window, errors_status

local function UpdateErrorsBadge()
	if not errors_btn then return end
	local count = #APHCR.error_log
	errors_btn:SetText(count > 0 and string.format("Errors (%d)", count) or "Errors")
end
on_error_logged = UpdateErrorsBadge

local function BuildErrorsText(limit)
	local blocks = {}
	for index, entry in ipairs(APHCR.error_log) do
		local repeats = entry.count > 1 and string.format(" (x%d)", entry.count) or ""
		local source = entry.run == 0 and "CodeRunner" or ("Run " .. entry.run)
		blocks[index] = { entry = entry, text = string.format("[%s] %s%s: %s", entry.time, source, repeats, entry.message) }
	end
	local first_shown = 1
	local function Total()
		local total = 0
		for index = first_shown, #blocks do total = total + #blocks[index].text + 2 end
		return total
	end
	while first_shown < #blocks and Total() > limit - 100 do first_shown = first_shown + 1 end
	local parts = {}
	if first_shown > 1 then
		parts[1] = string.format("(%d older errors hidden: ESO edit boxes hold at most %d characters)", first_shown - 1, limit)
	end
	for index = first_shown, #blocks do
		local text = blocks[index].text
		if #text > limit - 100 then text = text:sub(1, limit - 100) end
		parts[#parts + 1] = text
	end
	if #parts == 0 then parts[1] = "No errors." end
	return table.concat(parts, "\n\n")
end

local function RefreshErrors()
	local text = BuildErrorsText(errors_view.max_chars)
	errors_status:SetText(string.format("%d error(s) - updates every second", #APHCR.error_log))
	errors_view:SetText(text, true)
end

local function BuildErrorsWindow()
	errors_window, errors_status = MakeTextWindow("APHCodeRunnerErrors", "Errors")
	local clear_btn = MakeButton("APHCodeRunnerErrorsClear", errors_window, "Clear", 80, function()
		APHCR.ClearErrors()
		RefreshErrors()
	end)
	clear_btn:SetAnchor(TOPLEFT, errors_window, TOPLEFT, 12, 40)

	errors_view = MakeScrollText(errors_window, "APHCodeRunnerErrors", { read_only = true })
	errors_view.area:SetAnchor(TOPLEFT, clear_btn, BOTTOMLEFT, 0, 8)
	errors_view.area:SetAnchor(BOTTOMRIGHT, errors_status, TOPRIGHT, 0, -8)

	On(errors_window, "OnShow", function()
		errors_view:Relayout()
		RefreshErrors()
		Every("APHCodeRunnerErrors", VIEWER_REFRESH_MS, RefreshErrors)
	end, "errors show")
	On(errors_window, "OnHide", function()
		EVENT_MANAGER:UnregisterForUpdate("APHCodeRunnerErrors")
	end, "errors hide")
end

local STACK_GAP = 6
local STACK_MIN_HEIGHT = 260
local CASCADE_OFFSET = 36

local function PlaceErrorsWindow()
	errors_window.libaph_dock = nil
	errors_window:ClearAnchors()
	if not (viewer and not viewer:IsHidden()) then
		LibAPH.DockWindowBeside(errors_window, win, STACK_GAP, "left")
		return
	end
	local room_below = GuiRoot:GetHeight() - viewer:GetBottom() - STACK_GAP - 10
	if room_below >= STACK_MIN_HEIGHT then
		errors_window:SetDimensions(viewer:GetWidth(), math.min(errors_window:GetHeight(), room_below))
		errors_window:SetAnchor(TOPLEFT, GuiRoot, TOPLEFT, viewer:GetLeft(), viewer:GetBottom() + STACK_GAP)
	elseif viewer:GetLeft() >= errors_window:GetWidth() + STACK_GAP then
		errors_window:SetAnchor(TOPRIGHT, GuiRoot, TOPLEFT, viewer:GetLeft() - STACK_GAP, viewer:GetTop())
	else
		errors_window:SetAnchor(TOPLEFT, GuiRoot, TOPLEFT, viewer:GetLeft() + CASCADE_OFFSET, viewer:GetTop() + CASCADE_OFFSET)
	end
end

local function ToggleErrors()
	if not errors_window then BuildErrorsWindow() end
	if errors_window:IsHidden() then PlaceErrorsWindow() end
	errors_window:SetHidden(not errors_window:IsHidden())
	LeaveUIModeIfIdle()
end

local function ToggleViewer()
	if not viewer then BuildViewer() end
	if viewer:IsHidden() then LibAPH.DockWindowBeside(viewer, win, STACK_GAP, "left") end
	viewer:SetHidden(not viewer:IsHidden())
	if not viewer:IsHidden() and errors_window and not errors_window:IsHidden() then
		zo_callLater(Safe("restack errors", PlaceErrorsWindow), 50)
	end
	LeaveUIModeIfIdle()
end

local function ApplyMenuMode()
	local scenes = { "hud", "hudui" }
	if sv.show_in_menus then
		LibAPH.RemoveFragmentFromScenes(menu_fragment, scenes)
		win:SetHidden(not wanted_open)
	else
		LibAPH.AddFragmentToScenes(menu_fragment, scenes)
		local scene = SCENE_MANAGER:GetCurrentScene()
		win:SetHidden(not (wanted_open and scene and scene:HasFragment(menu_fragment)))
	end
end

local function EnterUIMode()
	if not SCENE_MANAGER:IsInUIMode() then SCENE_MANAGER:SetInUIMode(true) end
end

LeaveUIModeIfIdle = function()
	if wanted_open then return end
	if (viewer and not viewer:IsHidden()) or (errors_window and not errors_window:IsHidden()) then return end
	local scene = SCENE_MANAGER:GetCurrentScene()
	local scene_name = scene and scene:GetName()
	if (scene_name == "hud" or scene_name == "hudui") and SCENE_MANAGER:IsInUIMode() then
		SCENE_MANAGER:SetInUIMode(false)
	end
end

local function SetWindowOpen(open)
	wanted_open = open
	menu_fragment:SetHiddenForReason(CLOSED_REASON, not open)
	ApplyMenuMode()
	if open then EnterUIMode() else LeaveUIModeIfIdle() end
end

local function JumpToLocation(location)
	if not location or not win then return false end
	local index
	if files[location.index] and files[location.index].title == location.title then
		index = location.index
	else
		for file_index, file in ipairs(files) do
			if file.title == location.title then
				index = file_index
				break
			end
		end
	end
	if not index then return false end
	SetWindowOpen(true)
	SelectFile(index)
	editor:HighlightLine(location.line)
	SetStatus(false, string.format("%s line %d", location.title, location.line))
	return true
end

local SUGGEST_MAX = 8
local SUGGEST_IDLE_TEXT = "Autocomplete: type 2 letters, or press . or : after a name"
local SUGGEST_COLORS = {
	["function"] = "DCDCAA", table = "4EC9B0", userdata = "4EC9B0",
	number = "4FC1FF", string = "4FC1FF", boolean = "4FC1FF", word = "9CDCFE",
}
local suggest_bar, suggest_hint
local suggest_labels = {}
local suggestions = {}

local function ResolveChain(chain, text)
	local parts = {}
	for part in chain:gmatch("[%a_][%w_]*") do parts[#parts + 1] = part end
	if #parts == 0 then return nil end
	local function Walk(names)
		local value = _G
		for _, name in ipairs(names) do
			if type(value) ~= "table" and type(value) ~= "userdata" then return nil end
			local ok, member = pcall(function() return value[name] end)
			if not ok or member == nil then return nil end
			value = member
		end
		return value
	end
	local value = Walk(parts)
	if value == nil and rawget(_G, parts[1]) == nil then
		local alias = text:match("local%s+" .. parts[1] .. "%s*=%s*([%a_][%w_%.]*)")
		if alias then
			local names = {}
			for part in alias:gmatch("[%a_][%w_]*") do names[#names + 1] = part end
			for index = 2, #parts do names[#names + 1] = parts[index] end
			value = Walk(names)
		end
	end
	return value
end

local MAX_SKIPPED_PRIVATE = 20000
local global_entries
local autocomplete_broken = false

local function EachKey(container, visit)
	local key, skipped = nil, 0
	while true do
		local ok, next_key, value = pcall(next, container, key)
		if ok then
			if next_key == nil then return true end
			key = next_key
			visit(key, value)
		else
			local private_name = tostring(next_key):match("private function '([^']+)'")
			skipped = skipped + 1
			if not private_name or skipped > MAX_SKIPPED_PRIVATE then return false end
			key = private_name
			visit(private_name, nil, "function")
		end
	end
end

local function GlobalEntries()
	if global_entries then return global_entries end
	local entries = {}
	EachKey(_G, function(key, value, forced_kind)
		if type(key) == "string" and #key >= 2 then
			entries[#entries + 1] = { name = key, kind = forced_kind or type(value) }
		end
	end)
	if #entries == 0 then autocomplete_broken = true end
	global_entries = entries
	return entries
end

local function CollectSuggestions(prefix, owner, text)
	local lower_prefix = prefix:lower()
	local length = #lower_prefix
	local found, seen = {}, {}
	local function Consider(name, kind)
		if seen[name] or name == prefix or #found >= 4000 then return end
		if name:sub(1, length):lower() ~= lower_prefix then return end
		seen[name] = true
		found[#found + 1] = { name = name, kind = kind }
	end
	if owner ~= nil then
		local function FromTable(container)
			EachKey(container, function(key, value, forced_kind)
				if type(key) == "string" then Consider(key, forced_kind or type(value)) end
			end)
		end
		if type(owner) == "table" then FromTable(owner) end
		local ok, meta = pcall(getmetatable, owner)
		if ok and type(meta) == "table" and type(meta.__index) == "table" then FromTable(meta.__index) end
	else
		for word in text:gmatch("[%a_][%w_]*") do
			if #word >= 2 then Consider(word, "word") end
		end
		for _, entry in ipairs(GlobalEntries()) do
			Consider(entry.name, entry.kind)
		end
	end
	table.sort(found, function(a, b)
		local a_exact, b_exact = a.name:sub(1, length) == prefix, b.name:sub(1, length) == prefix
		if a_exact ~= b_exact then return a_exact end
		if #a.name ~= #b.name then return #a.name < #b.name end
		return a.name < b.name
	end)
	return found
end

local function HideSuggestions()
	suggestions = {}
	for _, label in ipairs(suggest_labels) do label:SetHidden(true) end
	if suggest_hint then
		suggest_hint:SetText(autocomplete_broken and "Autocomplete is unavailable here" or SUGGEST_IDLE_TEXT)
	end
end

local function UpdateSuggestions()
	if not (editor and suggest_bar) then return end
	local box = editor.box
	if autocomplete_broken or not box:HasFocus() then
		HideSuggestions()
		return
	end
	local text = box:GetText()
	local before = text:sub(1, box:GetCursorPosition())
	local prefix = before:match("[%a_][%w_]*$") or ""
	local head = before:sub(1, #before - #prefix)
	local chain = head:match("([%a_][%w_%.]*)[%.:]$")
	if not chain and #prefix < 2 then
		HideSuggestions()
		return
	end
	local owner
	if chain then
		owner = ResolveChain(chain, text)
		if owner == nil then
			HideSuggestions()
			return
		end
	end
	local found = CollectSuggestions(prefix, owner, text)
	suggestions = {}
	if autocomplete_broken then
		HideSuggestions()
		return
	end
	if #found == 0 then
		HideSuggestions()
		return
	end
	suggest_hint:SetText("Tab:")
	local room = suggest_bar:GetWidth() - suggest_hint:GetTextWidth() - 24
	local used, previous = 0, suggest_hint
	for index, item in ipairs(found) do
		if index > SUGGEST_MAX then break end
		local label = suggest_labels[index]
		label:SetText("|c" .. (SUGGEST_COLORS[item.kind] or "9CDCFE") .. item.name .. "|r")
		local width = label:GetTextWidth() + 14
		if used + width > room and #suggestions > 0 then break end
		used = used + width
		label:ClearAnchors()
		label:SetAnchor(LEFT, previous, RIGHT, 14, 0)
		label:SetHidden(false)
		suggestions[#suggestions + 1] = item
		previous = label
	end
	for index = #suggestions + 1, #suggest_labels do suggest_labels[index]:SetHidden(true) end
end

local function AcceptSuggestion(index)
	local item = suggestions[index]
	if not item then return end
	local box = editor.box
	local text = box:GetText()
	local cursor = box:GetCursorPosition()
	local prefix = text:sub(1, cursor):match("[%a_][%w_]*$") or ""
	HideSuggestions()
	if item.name:sub(1, #prefix) == prefix then
		box:InsertText(item.name:sub(#prefix + 1))
	else
		editor:ReplaceText(text:sub(1, cursor - #prefix) .. item.name .. text:sub(cursor + 1), cursor - #prefix + #item.name)
	end
	box:TakeFocus()
end

local function Build()
	win = WINDOW_MANAGER:CreateTopLevelWindow("APHCodeRunnerWindow")
	win:SetDimensions(780, 540)
	win:SetAnchor(CENTER, GuiRoot, CENTER, 0, 0)
	win:SetClampedToScreen(true)
	win:SetMouseEnabled(true)
	win:SetMovable(true)
	win:SetDrawTier(DT_MEDIUM)
	win:SetDrawLayer(DL_OVERLAY)
	win:SetDrawLevel(9100)
	win:SetHidden(true)
	On(win, "OnHide", PersistAll, "window hide")
	On(win, "OnShow", function()
		for _, view in ipairs(views) do view:Relayout() end
	end, "window show")

	menu_fragment = ZO_HUDFadeSceneFragment:New(win)
	menu_fragment:SetHiddenForReason(CLOSED_REASON, true)

	LibAPH.ApplyPanelBackdrop(win, "APHCodeRunnerWindowBG", LibAPH.THEME.BG)
	LibAPH.CreateHeaderStrip(win, "APHCodeRunnerWindowHeader", 30)
	local close = LibAPH.CreateThemedCloseButton(win, "APHCodeRunnerWindowClose", function() SetWindowOpen(false) end, 12, 10)
	LibAPH.MakeWindowResizable(win, { minWidth = 620, minHeight = 420 })

	MakeLabel(win, "APH Code Runner", 16):SetAnchor(TOPLEFT, win, TOPLEFT, 12, 8)

	local font_items = {}
	local font_index = 1
	for index, size in ipairs(FONT_SIZES) do
		font_items[index] = "Font " .. size
		if size == sv.font_size then font_index = index end
	end
	local font_container = MakeCombo("APHCodeRunnerFontCombo", win, 76, font_items, font_index, function(index)
		sv.font_size = FONT_SIZES[index]
		for _, view in ipairs(views) do view:ApplyFont() end
	end)
	font_container:SetAnchor(RIGHT, close, LEFT, -12, 0)

	local menu_label = MakeLabel(win, "Show in menus", 13, nil, "APHCodeRunnerMenuLabel")
	menu_label:SetMouseEnabled(true)
	menu_label:SetAnchor(RIGHT, font_container, LEFT, -14, 0)
	local menu_check = WINDOW_MANAGER:CreateControlFromVirtual("APHCodeRunnerMenuCheck", win, "ZO_CheckButton")
	menu_check:SetAnchor(RIGHT, menu_label, LEFT, -6, 0)
	ZO_CheckButton_SetCheckState(menu_check, sv.show_in_menus)
	local function SetShowInMenus(show)
		sv.show_in_menus = show
		ZO_CheckButton_SetCheckState(menu_check, show)
		ApplyMenuMode()
	end
	ZO_CheckButton_SetToggleFunction(menu_check, Safe("menu toggle", function(_, checked) SetShowInMenus(checked) end))
	On(menu_label, "OnMouseUp", function(_, button, upInside)
		if upInside and button == MOUSE_BUTTON_INDEX_LEFT then SetShowInMenus(not sv.show_in_menus) end
	end, "menu label")

	local chat_label = MakeLabel(win, "Chat Logs", 13, nil, "APHCodeRunnerChatLabel")
	chat_label:SetMouseEnabled(true)
	chat_label:SetAnchor(RIGHT, menu_check, LEFT, -14, 0)
	local chat_check = WINDOW_MANAGER:CreateControlFromVirtual("APHCodeRunnerChatCheck", win, "ZO_CheckButton")
	chat_check:SetAnchor(RIGHT, chat_label, LEFT, -6, 0)
	ZO_CheckButton_SetCheckState(chat_check, sv.chat_logs ~= false)
	local function SetChatLogs(on)
		sv.chat_logs = on
		ZO_CheckButton_SetCheckState(chat_check, on)
	end
	ZO_CheckButton_SetToggleFunction(chat_check, Safe("chat toggle", function(_, checked) SetChatLogs(checked) end))
	On(chat_label, "OnMouseUp", function(_, button, upInside)
		if upInside and button == MOUSE_BUTTON_INDEX_LEFT then SetChatLogs(sv.chat_logs == false) end
	end, "chat label")

	local footer = WINDOW_MANAGER:CreateControl(nil, win, CT_CONTROL)
	footer:SetHeight(30)
	footer:SetAnchor(BOTTOMLEFT, win, BOTTOMLEFT, 12, -10)
	footer:SetAnchor(BOTTOMRIGHT, win, BOTTOMRIGHT, -12, -10)

	local run_btn = MakeButton("APHCodeRunnerRunBtn", footer, "Run All", 90, function()
		PersistAll()
		local ok, message, location = APHCR.RunFiles(files, addon_box:GetText(), saved_box:GetText())
		SetStatus(ok, message)
		editor:UpdateGutter()
		if location then JumpToLocation(location) end
	end)
	run_btn:SetAnchor(BOTTOMLEFT, footer, BOTTOMLEFT, 0, 0)
	local stop_btn = MakeButton("APHCodeRunnerStopBtn", footer, "Stop", 70, function()
		PersistAll()
		APHCR.StopLast()
		ReloadUI("ingame")
	end)
	stop_btn:SetAnchor(BOTTOMLEFT, run_btn, BOTTOMRIGHT, 6, 0)
	local stop_all_btn = MakeButton("APHCodeRunnerStopAllBtn", footer, "Terminate All", 110, function()
		PersistAll()
		APHCR.StopAll()
		ReloadUI("ingame")
	end)
	stop_all_btn:SetAnchor(BOTTOMLEFT, stop_btn, BOTTOMRIGHT, 6, 0)
	local viewer_btn = MakeButton("APHCodeRunnerViewerBtn", footer, "SavedVars", 100, ToggleViewer)
	viewer_btn:SetAnchor(BOTTOMLEFT, stop_all_btn, BOTTOMRIGHT, 6, 0)
	errors_btn = MakeButton("APHCodeRunnerErrorsBtn", footer, "Errors", 100, ToggleErrors)
	errors_btn:SetAnchor(BOTTOMLEFT, viewer_btn, BOTTOMRIGHT, 6, 0)
	UpdateErrorsBadge()

	status_lbl = MakeLabel(footer, "", 13, LibAPH.THEME.MUTED)
	status_lbl:SetWrapMode(TEXT_WRAP_MODE_ELLIPSIS)
	status_lbl:SetVerticalAlignment(TEXT_ALIGN_CENTER)
	status_lbl:SetAnchor(TOPLEFT, errors_btn, TOPRIGHT, 10, 0)
	status_lbl:SetAnchor(BOTTOMRIGHT, footer, BOTTOMRIGHT, 0, 0)

	local side = WINDOW_MANAGER:CreateControl(nil, win, CT_CONTROL)
	side:SetWidth(190)
	side:SetAnchor(TOPLEFT, win, TOPLEFT, 12, 40)
	side:SetAnchor(BOTTOMLEFT, footer, TOPLEFT, 0, -10)

	MakeLabel(side, "Files, in load order", 13, LibAPH.THEME.MUTED):SetAnchor(TOPLEFT, side, TOPLEFT, 0, 0)

	local add_btn = MakeButton("APHCodeRunnerAddBtn", side, "Add", 92, function()
		files[#files + 1] = { title = "file" .. (#files + 1) .. ".lua", enabled = true, text = "" }
		PersistAll()
		list_offset = #files
		SelectFile(#files)
	end)
	local remove_btn = MakeButton("APHCodeRunnerRemoveBtn", side, "Remove", 92, function()
		if #files <= 1 then
			files[1] = { title = "main.lua", enabled = true, text = "" }
		else
			table.remove(files, selected)
		end
		PersistAll()
		SelectFile(selected)
	end)
	local up_btn = MakeButton("APHCodeRunnerUpBtn", side, "Up", 92, function()
		if selected <= 1 then return end
		files[selected], files[selected - 1] = files[selected - 1], files[selected]
		PersistAll()
		SelectFile(selected - 1)
	end)
	local down_btn = MakeButton("APHCodeRunnerDownBtn", side, "Down", 92, function()
		if selected >= #files then return end
		files[selected], files[selected + 1] = files[selected + 1], files[selected]
		PersistAll()
		SelectFile(selected + 1)
	end)
	up_btn:SetAnchor(BOTTOMLEFT, side, BOTTOMLEFT, 0, 0)
	down_btn:SetAnchor(LEFT, up_btn, RIGHT, 6, 0)
	add_btn:SetAnchor(BOTTOMLEFT, up_btn, TOPLEFT, 0, -6)
	remove_btn:SetAnchor(LEFT, add_btn, RIGHT, 6, 0)

	local list = WINDOW_MANAGER:CreateControl(nil, side, CT_CONTROL)
	list:SetAnchor(TOPLEFT, side, TOPLEFT, 0, 22)
	list:SetAnchor(BOTTOMRIGHT, add_btn, TOPLEFT, 190, -8)
	list:SetMouseEnabled(true)
	local function ScrollList(_, delta)
		list_offset = list_offset - delta
		RefreshList()
	end
	On(list, "OnMouseWheel", ScrollList, "file list wheel")
	LibAPH.ApplyPanelBackdrop(list, "APHCodeRunnerListBG", LibAPH.THEME.INSET)
	list_bar = MakeScrollbar(side, "APHCodeRunnerList", list, {
		inside = true,
		set_position = function(value)
			list_offset = math.floor(value + 0.5)
			RefreshList()
		end,
		page = function() return math.max(#list_rows - 1, 1) end,
		wheel_step = 1,
	})

	list_rows = {}
	local function BuildRows()
		local wanted = math.max(math.floor((list:GetHeight() - 8) / ROW_HEIGHT), 1)
		for index = #row_pool + 1, wanted do
			local row = WINDOW_MANAGER:CreateControl(nil, list, CT_CONTROL)
			row:SetHeight(ROW_HEIGHT)
			row:SetAnchor(TOPLEFT, list, TOPLEFT, 6, 4 + (index - 1) * ROW_HEIGHT)
			row:SetAnchor(TOPRIGHT, list, TOPRIGHT, -(6 + BAR_HIT_WIDTH), 4 + (index - 1) * ROW_HEIGHT)
			row:SetMouseEnabled(true)
			On(row, "OnMouseUp", function(self, button, upInside)
				if upInside and button == MOUSE_BUTTON_INDEX_LEFT and files[self.file_index] then SelectFile(self.file_index) end
			end, "file row")
			On(row, "OnMouseWheel", ScrollList, "file row wheel")

			local check = WINDOW_MANAGER:CreateControlFromVirtual("APHCodeRunnerRowCheck" .. index, row, "ZO_CheckButton")
			check:SetAnchor(LEFT, row, LEFT, 0, 0)
			On(check, "OnMouseWheel", ScrollList, "file check wheel")
			ZO_CheckButton_SetToggleFunction(check, Safe("file check", function(_, checked)
				local file = files[row.file_index]
				if not file then return end
				file.enabled = checked
				PersistFile(row.file_index)
				RefreshList()
			end))

			local label = MakeLabel(row, "", 13)
			label:SetHeight(ROW_HEIGHT)
			label:SetVerticalAlignment(TEXT_ALIGN_CENTER)
			label:SetWrapMode(TEXT_WRAP_MODE_ELLIPSIS)
			label:SetAnchor(LEFT, check, RIGHT, 6, 0)
			label:SetAnchor(RIGHT, row, RIGHT, 0, 0)

			row.check, row.label = check, label
			row_pool[index] = row
		end
		list_rows = {}
		for index, row in ipairs(row_pool) do
			if index <= wanted then list_rows[index] = row else row:SetHidden(true) end
		end
		RefreshList()
	end
	On(list, "OnRectChanged", BuildRows, "file list resize")

	local header_row = WINDOW_MANAGER:CreateControl(nil, win, CT_CONTROL)
	header_row:SetHeight(26)
	header_row:SetAnchor(TOPLEFT, side, TOPRIGHT, 12, 0)
	header_row:SetAnchor(TOPRIGHT, win, TOPRIGHT, -12, 40)

	local addon_bg
	addon_bg, addon_box = MakeLineEdit("APHCodeRunnerAddonName", header_row, "Add-on name (sent with EVENT_ADD_ON_LOADED)", function(self)
		sv.addon_name = self:GetText()
	end)
	addon_bg:SetAnchor(TOPLEFT, header_row, TOPLEFT, 0, 0)
	addon_bg:SetAnchor(TOPRIGHT, header_row, TOP, -4, 0)
	addon_box:SetText(sv.addon_name)

	local saved_bg
	saved_bg, saved_box = MakeLineEdit("APHCodeRunnerSavedNames", header_row, "SavedVariables names, from the manifest", function(self)
		sv.saved_names = self:GetText()
	end)
	saved_bg:SetAnchor(TOPLEFT, header_row, TOP, 4, 0)
	saved_bg:SetAnchor(TOPRIGHT, header_row, TOPRIGHT, 0, 0)
	saved_box:SetText(sv.saved_names)

	local title_bg
	title_bg, title_box = MakeLineEdit("APHCodeRunnerFileTitle", win, "File name, e.g. Core/ALC_Core.lua", function(self)
		if not files[selected] or (editor and editor.loading) then return end
		files[selected].title = self:GetText()
		PersistFile(selected)
		RefreshList()
	end)
	title_bg:SetAnchor(TOPLEFT, header_row, BOTTOMLEFT, 0, 8)
	title_bg:SetAnchor(TOPRIGHT, header_row, BOTTOMRIGHT, -200, 8)
	chars_lbl = MakeLabel(win, "", 13, LibAPH.THEME.MUTED)
	chars_lbl:SetHorizontalAlignment(TEXT_ALIGN_RIGHT)
	chars_lbl:SetAnchor(RIGHT, header_row, BOTTOMRIGHT, 0, 21)

	local search_bg
	search_bg, search_box = MakeLineEdit("APHCodeRunnerSearch", win, "Search this file - Enter next, Shift+Enter previous", function()
		if reset_code_search then reset_code_search() end
	end)
	search_bg:SetAnchor(TOPLEFT, title_bg, BOTTOMLEFT, 0, 8)
	search_bg:SetAnchor(TOPRIGHT, title_bg, BOTTOMRIGHT, 0, 8)
	search_status = MakeLabel(win, "", 13, LibAPH.THEME.MUTED)
	search_status:SetAnchor(LEFT, search_bg, RIGHT, 8, 0)
	local redo_btn = MakeButton("APHCodeRunnerRedoBtn", win, "Redo", 52, function()
		editor.history:Redo()
		editor.box:TakeFocus()
	end)
	redo_btn:SetAnchor(TOPRIGHT, header_row, BOTTOMRIGHT, 0, 42)
	local undo_btn = MakeButton("APHCodeRunnerUndoBtn", win, "Undo", 52, function()
		editor.history:Undo()
		editor.box:TakeFocus()
	end)
	undo_btn:SetAnchor(RIGHT, redo_btn, LEFT, -4, 0)

	suggest_bar = WINDOW_MANAGER:CreateControl("APHCodeRunnerSuggest", win, CT_CONTROL)
	suggest_bar:SetHeight(24)
	suggest_bar:SetAnchor(BOTTOMLEFT, footer, TOPLEFT, 190 + 12, -8)
	suggest_bar:SetAnchor(BOTTOMRIGHT, footer, TOPRIGHT, 0, -8)
	LibAPH.ApplyPanelBackdrop(suggest_bar, "APHCodeRunnerSuggestBG", LibAPH.THEME.INSET)
	suggest_hint = MakeLabel(suggest_bar, SUGGEST_IDLE_TEXT, 13, LibAPH.THEME.MUTED)
	suggest_hint:SetAnchor(LEFT, suggest_bar, LEFT, 8, 0)

	editor = MakeScrollText(win, "APHCodeRunnerCode", {
		box_name = "APHCodeRunnerCodeBox",
		gutter = true,
		follow_cursor = true,
		undo = true,
		after_edit = UpdateSuggestions,
		marks = function()
			local file = files[selected]
			return file and file.error_lines or {}
		end,
		on_change = function(text)
			local file = files[selected]
			if not file then return end
			file.text = text
			file.error_lines = nil
			PersistFile(selected)
			RefreshCharCount()
		end,
	})
	editor.area:SetAnchor(TOPLEFT, search_bg, BOTTOMLEFT, 0, 8)
	editor.area:SetAnchor(BOTTOMRIGHT, suggest_bar, TOPRIGHT, 0, -6)
	reset_code_search = AttachSearch(search_box, search_status, editor.box, function(line)
		editor:ScrollToLine(line)
	end)

	ZO_PreHookHandler(editor.box, "OnTab", Safe("autocomplete tab", function()
		if #suggestions > 0 then
			AcceptSuggestion(1)
			return true
		end
	end))
	ZO_PostHookHandler(editor.box, "OnFocusLost", Safe("autocomplete blur", function()
		if not MouseIsOver(suggest_bar) then HideSuggestions() end
	end))
	for index = 1, SUGGEST_MAX do
		local label = MakeLabel(suggest_bar, "", 13)
		label:SetMouseEnabled(true)
		label:SetHidden(true)
		On(label, "OnMouseUp", function(_, button, upInside)
			if upInside and button == MOUSE_BUTTON_INDEX_LEFT then AcceptSuggestion(index) end
		end, "suggestion " .. index)
		suggest_labels[index] = label
	end

	BuildRows()
	SelectFile(selected)
	ApplyMenuMode()
end

local function Toggle()
	if not win then Build() end
	SetWindowOpen(not wanted_open)
end

local function HookReloadUI()
	local reloadui_key = GetString(SI_SLASH_RELOADUI)
	local original = SLASH_COMMANDS[reloadui_key]
	SLASH_COMMANDS[reloadui_key] = function(...)
		PersistAll()
		APHCR.StopAll()
		if original then original(...) end
	end
end

local function OnAddOnLoaded(_, name)
	if name ~= APHCR.name then return end
	EVENT_MANAGER:UnregisterForEvent(APHCR.name, EVENT_ADD_ON_LOADED)
	LibAPH.RegisterAddonDependencies(APHCR.name, { "LibAPH" }, {})
	sv = ZO_SavedVars:NewAccountWide("APHCodeRunner_SV", 1, nil, {
		files = {}, addon_name = "", saved_names = "", font_size = 13, show_in_menus = true, chat_logs = true,
	})
	LoadFiles()
	SLASH_COMMANDS["/coderunner"] = Toggle
	HookReloadUI()
end

EVENT_MANAGER:RegisterForEvent(APHCR.name, EVENT_ADD_ON_LOADED, OnAddOnLoaded)
