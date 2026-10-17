local projects_root, addon, mode, stubs_path, esoui_root, allowed_path = ...
assert(projects_root and addon and mode and stubs_path, "usage: smoke.lua <projects_root> <addon> <keyboard|gamepad|console> <stubs.lua> [esoui_root] [allowed.lua]")

local rawget, rawset, setmetatable, type, pairs, ipairs, tostring = rawget, rawset, setmetatable, type, pairs, ipairs, tostring

dofile(stubs_path)
local ALLOWED = { globals = {}, skip_commands = {}, run_commands = true, run_settings = true }
local function NameSet(text)
	local set = {}
	for name in tostring(text or ""):gmatch("[^,%s]+") do set[name] = true end
	return set
end
local OFF = NameSet(os.getenv("APH_SMOKE_OFF"))
local ON = NameSet(os.getenv("APH_SMOKE_ON"))
if allowed_path and allowed_path ~= "" then
	local chunk = assert(loadfile(allowed_path))
	local settings = {}
	setfenv(chunk, settings)
	local returned = chunk()
	for key, value in pairs(type(returned) == "table" and returned or settings) do ALLOWED[key] = value end
end
local allowed_globals = {}
for _, name in ipairs(ALLOWED.globals or {}) do allowed_globals[name] = true end
local skip_commands = {}
for _, name in ipairs(ALLOWED.skip_commands or {}) do skip_commands[name] = true end

local CONSOLE = mode == "console"
local GAMEPAD = mode ~= "keyboard"
local failures = {}
local function Fail(stage, message)
	failures[#failures + 1] = string.format("SMOKE FAIL [%s] %s: %s", mode, stage, tostring(message))
end

local now_ms = 100000
local stub_cache = {}
local Stub
local stub_meta = {}

local function Values(codes, name)
	if not codes or codes == "" then return nil end
	local out = {}
	for index = 1, #codes do
		local code = codes:sub(index, index)
		if code == "i" then out[index] = 0
		elseif code == "b" then out[index] = false
		elseif code == "s" then out[index] = ""
		elseif code == "n" then out[index] = nil
		else out[index] = Stub(name .. "()") end
	end
	return unpack(out, 1, #codes)
end

stub_meta.__index = function(self, key)
	if type(key) ~= "string" then return nil end
	local child = Stub(key)
	rawset(self, key, child)
	return child
end
local function EndsIteration(name)
	return name:find("^GetNext") ~= nil or name:find("^ZO_GetNext") ~= nil
end

stub_meta.__call = function(self)
	local name = rawget(self, "__stub_name")
	if EndsIteration(name) then return nil end
	local codes = ESO_METHODS[name]
	if codes ~= nil then return Values(codes, name) end
	if name:find("String", 1, true) or name:find("Text", 1, true) then return "" end
	return Stub(name .. "()")
end
stub_meta.__tostring = function(self) return "stub:" .. tostring(rawget(self, "__stub_name")) end

function Stub(name)
	return setmetatable({ __stub_name = name }, stub_meta)
end

local SELF_GLOBALS = {}
local function Provide(name, value)
	SELF_GLOBALS[name] = true
	rawset(_G, name, value)
end

local written = {}
local loading_esoui = false
local control_globals, string_globals = {}, {}
local KEYBOARD_ONLY = { ADD_ON_MANAGER = true }
setmetatable(_G, {
	__index = function(_, key)
		if type(key) ~= "string" then return nil end
		if CONSOLE and KEYBOARD_ONLY[key] then return nil end
		local cached = stub_cache[key]
		if cached ~= nil then return cached end
		local constant = ESO_CONSTANTS[key]
		if constant then
			stub_cache[key] = constant
			return constant
		end
		local codes = ESO_FUNCS[key]
		if codes then
			local fn = EndsIteration(key) and function() return nil end or function() return Values(codes, key) end
			stub_cache[key] = fn
			return fn
		end
		local literal = ESO_LUA_VALUES[key]
		if literal ~= nil then
			stub_cache[key] = literal
			return literal
		end
		if ESO_LUA_GLOBALS[key] then
			local stub = Stub(key)
			stub_cache[key] = stub
			return stub
		end
		return nil
	end,
	__newindex = function(_, key, value)
		if not loading_esoui then written[key] = true end
		rawset(_G, key, value)
	end,
})

local events, updates, later = {}, {}, {}
local later_id = 0
Provide("EVENT_MANAGER", {
	RegisterForEvent = function(_, namespace, event, fn)
		if event == nil then error("RegisterForEvent(" .. tostring(namespace) .. ") got a nil event", 2) end
		events[event] = events[event] or {}
		events[event][namespace] = fn
		return true
	end,
	UnregisterForEvent = function(_, namespace, event)
		if event == nil then
			for _, handlers in pairs(events) do handlers[namespace] = nil end
		elseif events[event] then
			events[event][namespace] = nil
		end
		return true
	end,
	AddFilterForEvent = function() return true end,
	RegisterForUpdate = function(_, namespace, interval, fn, once)
		updates[namespace] = { interval = interval or 0, fn = fn, last = now_ms, once = once }
		return true
	end,
	UnregisterForUpdate = function(_, namespace) updates[namespace] = nil return true end,
})
Provide("zo_callLater", function(fn, delay)
	later_id = later_id + 1
	later[#later + 1] = { at = now_ms + (delay or 0), fn = fn, id = later_id }
	return later_id
end)
Provide("zo_removeCallLater", function(id)
	for index = #later, 1, -1 do if later[index].id == id then table.remove(later, index) end end
end)

Provide("IsConsoleUI", function() return CONSOLE end)
Provide("LocaleAwareToUpper", string.upper)
Provide("LocaleAwareToLower", string.lower)
Provide("zo_strtrim", function(str) return (string.gsub(str, "^%s*(.-)%s*$", "%1")) end)
Provide("IsInGamepadPreferredMode", function() return GAMEPAD end)
Provide("IsKeyboardUISupported", function() return not CONSOLE end)
Provide("GetGameTimeMilliseconds", function() return now_ms end)
Provide("GetFrameTimeMilliseconds", function() return now_ms end)
Provide("GetGameTimeSeconds", function() return now_ms / 1000 end)
Provide("GetFrameTimeSeconds", function() return now_ms / 1000 end)
Provide("GetTimeStamp", function() return 1790000000 end)
Provide("GetWorldName", function() return "NA Megaserver" end)
Provide("GetDisplayName", function() return "@AuditTester" end)
Provide("GetUnitName", function() return "Audit Tester" end)
Provide("GetCurrentCharacterId", function() return "8796093022208" end)
Provide("GetCVar", function() return "" end)
Provide("GetUIGlobalScale", function() return 1 end)
Provide("GetTotalUserAddOnMemoryPoolUsageMB", function() return 20 end)
Provide("GetTotalUserAddOnMemoryPoolCapacityMB", function() return 100 end)
Provide("GetTotalUserAddOnCPUTimeAvailableEachFrameMS", function() return 1000 end)
Provide("GetTotalUserAddOnCPUTimeUsedNowMS", function() return 0 end)
Provide("d", function() end)
Provide("SLASH_COMMANDS", {})

local strings = {}
Provide("ZO_CreateStringId", function(key, value)
	string_globals[key] = true
	rawset(_G, key, key)
	strings[key] = value
end)
Provide("SafeAddString", function(key, value) if key then strings[key] = value end end)
Provide("SafeAddVersion", function() end)
Provide("GetString", function(key, index)
	if type(key) == "string" and index ~= nil then return key .. tostring(index) end
	return strings[key] or (type(key) == "string" and key or "")
end)
Provide("zo_strformat", function(format, ...)
	local args = { ... }
	format = strings[format] or format
	if type(format) ~= "string" then format = tostring(format) end
	return (format:gsub("<<[^>]-(%d+)>>", function(slot) return tostring(args[tonumber(slot)] or "") end))
end)
Provide("ZO_CachedStrFormat", function(format, ...) return zo_strformat(format, ...) end)

local function DeepCopy(source)
	local copy = {}
	for key, value in pairs(source or {}) do copy[key] = type(value) == "table" and DeepCopy(value) or value end
	return copy
end
local function SavedTable(_, _, _, _, defaults)
	return DeepCopy(defaults)
end
Provide("ZO_SavedVars", { NewAccountWide = SavedTable, NewCharacterIdSettings = SavedTable,
	NewCharacterNameSettings = SavedTable, New = SavedTable })

local control_meta = {}
local text_fit = { labels = {}, textures = {}, cut = {}, char_w = 8 }
local function Control(name, parent)
	local control = Stub(name or "control")
	rawset(control, "__stub_name", name or "control")
	local left, top, width, height, hidden, text = 0, 0, 100, 20, false, ""
	local font = ""
	local handlers = {}
	local function CharWidth()
		local size = tonumber(font:match("|(%d+)"))
		return size and size * 0.57 or text_fit.char_w
	end
	rawset(control, "SetFont", function(_, value) font = tostring(value or "") end)
	rawset(control, "SetDrawLevel", function(_, value) rawset(control, "__level", tonumber(value) or 0) end)
	rawset(control, "GetDrawLevel", function() return rawget(control, "__level") or 0 end)
	rawset(control, "SetDrawLayer", function(_, value) rawset(control, "__layer", value) end)
	rawset(control, "GetDrawLayer", function() return rawget(control, "__layer") end)
	rawset(control, "GetFont", function() return font end)
	rawset(control, "__char_w", CharWidth)
	rawset(control, "GetName", function() return name or "" end)
	rawset(control, "GetParent", function() return parent end)
	rawset(control, "SetHidden", function(_, value) hidden = value and true or false end)
	rawset(control, "IsHidden", function() return hidden end)
	rawset(control, "SetText", function(_, value) text = tostring(value or "") end)
	rawset(control, "GetText", function() return text end)
	rawset(control, "SetDimensions", function(_, w, h) width, height = w or width, h or height rawset(control, "__width_set", w ~= nil) end)
	rawset(control, "SetWidth", function(_, w) width = w or width rawset(control, "__width_set", w ~= nil) end)
	rawset(control, "SetMaxLineCount", function(_, value) rawset(control, "__max_lines", tonumber(value) or 0) end)
	rawset(control, "SetHeight", function(_, h) height = h or height end)
	rawset(control, "GetWidth", function() return width end)
	rawset(control, "GetHeight", function() return height end)
	rawset(control, "GetDimensions", function() return width, height end)
	rawset(control, "GetLeft", function() return left end)
	rawset(control, "GetTop", function() return top end)
	rawset(control, "GetRight", function() return left + width end)
	rawset(control, "GetBottom", function() return top + height end)
	rawset(control, "GetCenter", function() return left + width / 2, top + height / 2 end)
	rawset(control, "GetTextWidth", function() return #text * CharWidth() end)
	rawset(control, "GetTextHeight", function() return 18 end)
	rawset(control, "GetTextDimensions", function() return #text * CharWidth(), 18 end)
	rawset(control, "GetStringWidth", function(_, value) return #tostring(value or "") * CharWidth() end)
	rawset(control, "SetHandler", function(_, event, fn) handlers[event] = fn end)
	rawset(control, "GetHandler", function(_, event) return handlers[event] end)
	rawset(control, "GetNamedChild", function(_, suffix) return _G[(name or "") .. suffix] or Control((name or "") .. suffix, control) end)
	rawset(control, "GetNumChildren", function() return 0 end)
	if name and name ~= "" then
		control_globals[name] = true
		rawset(_G, name, control)
	end
	return setmetatable(control, control_meta)
end
control_meta.__index = stub_meta.__index
control_meta.__call = stub_meta.__call

for _, native_name in ipairs({ "ZO_Compass", "ZO_CompassFrame", "ZO_CollectionsBook_TopLevelSearchBox" }) do
	Control(native_name)
	control_globals[native_name] = true
end

Provide("WINDOW_MANAGER", setmetatable({
	CreateControl = function(_, name, parent, kind)
		local control = Control(name, parent)
		if kind ~= nil and kind == CT_LABEL then text_fit.labels[#text_fit.labels + 1] = control end
		if kind ~= nil and kind == CT_TEXTURE then text_fit.textures[#text_fit.textures + 1] = control end
		return control
	end,
	CreateControlFromVirtual = function(_, name, parent, _, suffix) return Control(name and (name .. (suffix or "")) or nil, parent) end,
	CreateTopLevelWindow = function(_, name) return Control(name) end,
	GetControlByName = function(_, name) return rawget(_G, name) end,
	GetMouseOverControl = function() return nil end,
}, stub_meta))
Provide("GuiRoot", Control("GuiRoot"))
GuiRoot:SetDimensions(1920, 1080)

local callbacks = {}
Provide("CALLBACK_MANAGER", setmetatable({
	RegisterCallback = function(_, name, fn) callbacks[name] = callbacks[name] or {}; table.insert(callbacks[name], fn) end,
	UnregisterCallback = function() end,
	FireCallbacks = function(_, name, ...)
		for _, fn in ipairs(callbacks[name] or {}) do fn(...) end
	end,
}, stub_meta))

local scenes = {}
local function Scene(name)
	if scenes[name] then return scenes[name] end
	local scene = Stub(name)
	local listeners, state = {}, "hidden"
	rawset(scene, "RegisterCallback", function(_, event, fn) if event == "StateChange" then listeners[#listeners + 1] = fn end end)
	rawset(scene, "UnregisterCallback", function() end)
	rawset(scene, "GetName", function() return name end)
	rawset(scene, "GetState", function() return state end)
	rawset(scene, "IsShowing", function() return state == "showing" or state == "shown" end)
	rawset(scene, "IsInstanceOf", function() return true end)
	rawset(scene, "__fire", function(new_state)
		local old = state
		state = new_state
		for _, fn in ipairs(listeners) do fn(old, new_state) end
	end)
	scenes[name] = scene
	return scene
end
Provide("SCENE_MANAGER", setmetatable({
	GetScene = function(_, name) return Scene(name) end,
	GetCurrentScene = function() return Scene("hud") end,
	IsShowing = function(_, name) return Scene(name):IsShowing() end,
	IsShowingBaseScene = function() return Scene("hud"):IsShowing() end,
	RegisterCallback = function() end,
}, stub_meta))
Provide("HUD_SCENE", Scene("hud"))
Provide("HUD_UI_SCENE", Scene("hudui"))

if esoui_root and esoui_root ~= "" then
	loading_esoui = true
	for _, file in ipairs({ "libraries/globals/globalapi.lua", "libraries/utility/baseobject.lua", "libraries/utility/zo_tableutils.lua", "libraries/utility/zo_hook.lua",
		"libraries/utility/zo_callbackobject.lua" }) do
		local ok, err = pcall(dofile, esoui_root .. "/" .. file)
		if not ok then Fail("esoui", "could not load " .. file .. ": " .. tostring(err)) end
	end
	loading_esoui = false
end

local settings_panels = {}
local lhas_settings = {}
if ON.LibHarvensAddonSettings and not OFF.LibHarvensAddonSettings then
	local lhas = { version = 20200, ST_CHECKBOX = 1, ST_SLIDER = 2, ST_EDIT = 3, ST_DROPDOWN = 4, ST_COLOR = 5, ST_BUTTON = 6,
		ST_LABEL = 7, ST_SECTION = 8, ST_ICONPICKER = 9, ST_ATLASICONPICKER = 10 }
	local function Nothing() end
	lhas.AddAddon = function(_, name, options)
		local panel = { name = name, options = options, settings = {} }
		panel.AddSetting = function(target, params)
			target.settings[#target.settings + 1] = params
			lhas_settings[#lhas_settings + 1] = params
			return params
		end
		panel.AddSettings = function(target, list)
			for _, params in ipairs(list) do target:AddSetting(params) end
			return list
		end
		panel.RemoveAllSettings = function(target) target.settings = {} end
		panel.RemoveSettings, panel.GetIndexOf, panel.Select, panel.ResetToDefaults = Nothing, Nothing, Nothing, Nothing
		panel.Clear, panel.UpdateControls = Nothing, Nothing
		return panel
	end
	lhas.RefreshAddonSettings, lhas.SelectFirstAddon, lhas.GoBack = Nothing, Nothing, Nothing
	Provide("LibHarvensAddonSettings", lhas)
end
if not OFF.LibAddonMenu2 then Provide("LibAddonMenu2", {
	RegisterAddonPanel = function(_, id) local panel = Control(id); settings_panels[#settings_panels + 1] = { id = id }; return panel end,
	RegisterOptionControls = function(_, id, data) settings_panels[#settings_panels + 1] = { id = id, data = data } end,
	util = Stub("LAM.util"),
}) end

local function Manifest(folder)
	local dir = projects_root .. "/" .. folder .. "/"
	local handle = io.open(dir .. folder .. ".addon") or io.open(dir .. folder .. ".txt")
	if not handle then return nil end
	local files, saved = {}, {}
	for line in handle:lines() do
		line = line:gsub("^\239\187\191", ""):gsub("%s+$", "")
		local vars = line:match("^##%s*SavedVariables%w*:%s*(.+)$")
		if vars then for name in vars:gmatch("%S+") do saved[name] = true end end
		local file = line:match("^([^#;].-%.lua)$")
		if file then
			local path = dir .. file:gsub("%$%(language%)", "en"):gsub("\\", "/")
			local exists = io.open(path)
			if exists then exists:close() end
			if exists or not file:find("$(language)", 1, true) then files[#files + 1] = path end
		end
	end
	handle:close()
	return files, saved
end

local function Run(stage, fn, ...)
	local count, args = select("#", ...), { ... }
	local ok, err = xpcall(function() return fn(unpack(args, 1, count)) end, debug.traceback)
	if not ok then Fail(stage, err) end
	return ok
end

local function Fire(event, ...)
	local list = {}
	for namespace, fn in pairs(events[event] or {}) do list[#list + 1] = { namespace, fn } end
	table.sort(list, function(a, b) return tostring(a[1]) < tostring(b[1]) end)
	for _, entry in ipairs(list) do Run(tostring(event) .. " " .. tostring(entry[1]), entry[2], event, ...) end
end

local function Frames(count)
	for _ = 1, count do
		now_ms = now_ms + 16
		local due = {}
		for namespace, update in pairs(updates) do
			if now_ms - update.last >= update.interval then due[#due + 1] = { namespace, update } end
		end
		for _, entry in ipairs(due) do
			entry[2].last = now_ms
			if entry[2].once and updates[entry[1]] == entry[2] then updates[entry[1]] = nil end
			Run("update " .. tostring(entry[1]), entry[2].fn, now_ms / 1000)
		end
		local ready = {}
		for index = #later, 1, -1 do
			if later[index].at <= now_ms then ready[#ready + 1] = table.remove(later, index) end
		end
		for index = #ready, 1, -1 do Run("zo_callLater", ready[index].fn, ready[index].id) end
	end
end

local folders = {}
for _, dep in ipairs(ALLOWED.libraries or {}) do if not OFF[dep] then folders[#folders + 1] = dep end end
for dep in pairs(ON) do
	local listed = false
	for _, folder in ipairs(folders) do if folder == dep then listed = true end end
	if not listed and dep ~= addon and Manifest(dep) then table.insert(folders, 1, dep) end
end
folders[#folders + 1] = addon

local saved_names = {}
for _, folder in ipairs(folders) do
	local files, saved = Manifest(folder)
	if not files then
		Fail("load", "no manifest for " .. folder)
	else
		for name in pairs(saved) do saved_names[name] = true end
		for _, path in ipairs(files) do
			local chunk, err = loadfile(path)
			if not chunk then Fail("load", err) else Run("load " .. path:sub(#projects_root + 2), chunk) end
		end
	end
end

for _, folder in ipairs(folders) do Fire(EVENT_ADD_ON_LOADED, folder) end
Fire(EVENT_ADD_ON_LOADED, "SomeOtherAddon")
Frames(60)
Fire(EVENT_PLAYER_ACTIVATED, true)
Frames(60)
Scene("hud").__fire("showing")
Scene("hud").__fire("shown")
Frames(60)

function text_fit.Shown(control)
	local seen = 0
	while control and seen < 50 do
		if control.IsHidden and control:IsHidden() then return false end
		control = control.GetParent and control:GetParent() or nil
		seen = seen + 1
	end
	return true
end
function text_fit.Check(stage)
	for _, label in ipairs(text_fit.labels) do
		local lines_allowed = rawget(label, "__max_lines") or 0
		if lines_allowed > 0 and rawget(label, "__width_set") and text_fit.Shown(label) then
			local width = label:GetWidth()
			local text = tostring(label:GetText() or ""):gsub("|c%x%x%x%x%x%x", ""):gsub("|r", "")
			if text ~= "" and width > 0 then
				local needed = 0
				local char_w = rawget(label, "__char_w")()
				for line in (text .. "\n"):gmatch("(.-)\n") do needed = needed + math.max(1, math.ceil(#line * char_w / width)) end
				local key = tostring(rawget(label, "__stub_name")) .. "|" .. text
				if needed > lines_allowed and not text_fit.cut[key] then
					text_fit.cut[key] = true
					Fail("text " .. stage, string.format("%s cuts off \"%s\" (needs %d lines at %d px, allowed %d)", tostring(rawget(label, "__stub_name")), text:sub(1, 80), needed, width, lines_allowed))
				end
			end
		end
	end
end
function text_fit.Layers(stage)
	local above = {}
	for _, texture in ipairs(text_fit.textures) do
		local parent = texture:GetParent()
		if parent and text_fit.Shown(texture) then
			local by_layer = above[parent] or {}
			above[parent] = by_layer
			local layer = tostring(rawget(texture, "__layer"))
			local level = rawget(texture, "__level") or 0
			if not by_layer[layer] or level > by_layer[layer].level then by_layer[layer] = { level = level, texture = texture } end
		end
	end
	for _, label in ipairs(text_fit.labels) do
		local parent = label:GetParent()
		local text = tostring(label:GetText() or "")
		local top = parent and above[parent] and above[parent][tostring(rawget(label, "__layer"))]
		if top and text ~= "" and text_fit.Shown(label) and top.level > (rawget(label, "__level") or 0) then
			local key = "layer|" .. tostring(rawget(label, "__stub_name")) .. "|" .. tostring(rawget(top.texture, "__stub_name"))
			if not text_fit.cut[key] then
				text_fit.cut[key] = true
				Fail("text " .. stage, string.format("%s (\"%s\") is drawn under %s (draw level %d over %d), so lines can run through the text", tostring(rawget(label, "__stub_name")), text:sub(1, 40), tostring(rawget(top.texture, "__stub_name")), top.level, rawget(label, "__level") or 0))
			end
		end
	end
end
function text_fit.PcFont(font)
	font = tostring(font or "")
	if font == "" then return nil end
	if font:find("^ZoFont") and not font:find("Gamepad", 1, true) then return font end
	if font:find("$(MEDIUM_FONT)", 1, true) or font:find("$(BOLD_FONT)", 1, true) or font:find("$(CHAT_FONT)", 1, true) or font:find("Univers", 1, true) then return font end
	return nil
end
function text_fit.ConsoleFonts(stage)
	if not CONSOLE then return end
	for _, label in ipairs(text_fit.labels) do
		local text = tostring(label:GetText() or "")
		local font = text ~= "" and text_fit.Shown(label) and text_fit.PcFont(label:GetFont())
		local key = "font|" .. tostring(rawget(label, "__stub_name")) .. "|" .. tostring(font)
		if font and not text_fit.cut[key] then
			text_fit.cut[key] = true
			Fail("text " .. stage, string.format("%s (\"%s\") uses the PC font %s on console; use a gamepad font (ZoFontGamepad..., $(GAMEPAD_MEDIUM_FONT) or $(GAMEPAD_BOLD_FONT))", tostring(rawget(label, "__stub_name")), text:sub(1, 40), font))
		end
	end
end
text_fit.Check("after the HUD shows")
text_fit.Layers("after the HUD shows")
text_fit.ConsoleFonts("after the HUD shows")

if ALLOWED.run_settings ~= false then
	for _, panel in ipairs(settings_panels) do
		local function Visit(list)
			for _, control in ipairs(list or {}) do
				if type(control.name) == "function" then Run("settings " .. panel.id, control.name) end
				if type(control.disabled) == "function" then Run("settings " .. panel.id, control.disabled) end
				if type(control.getFunc) == "function" then Run("settings " .. panel.id .. " " .. tostring(control.name), control.getFunc) end
				if type(control.text) == "function" then Run("settings " .. panel.id, control.text) end
				if control.controls then Visit(control.controls) end
			end
		end
		Visit(panel.data)
	end
	for _, params in ipairs(lhas_settings) do
		if params.type == nil then Fail("settings LibHarvensAddonSettings", "a setting has no type (" .. tostring(params.label) .. ")") end
		for _, key in ipairs({ "label", "tooltip", "getFunction", "disable" }) do
			if type(params[key]) == "function" then Run("settings LibHarvensAddonSettings " .. key, params[key]) end
		end
	end
end

if ALLOWED.run_commands ~= false then
	local names = {}
	for name in pairs(SLASH_COMMANDS) do names[#names + 1] = name end
	table.sort(names)
	for _, name in ipairs(names) do
		if not skip_commands[name] and SLASH_COMMANDS[name] then
			Run("slash " .. name, SLASH_COMMANDS[name], "")
			Frames(10)
		end
	end
end
Frames(120)
text_fit.Check("after slash commands")
text_fit.Layers("after slash commands")
text_fit.ConsoleFonts("after slash commands")

for name in pairs(written) do
	local known = ESO_CONSTANTS[name] or ESO_FUNCS[name] or ESO_LUA_GLOBALS[name] or ESO_LUA_VALUES[name] ~= nil or SELF_GLOBALS[name]
	if not known and not control_globals[name] and not string_globals[name] and not allowed_globals[name] and not saved_names[name] then
		failures[#failures + 1] = string.format("SMOKE LEAK [%s] global '%s' is created but not listed in .eso-auditrc globals", mode, name)
	end
end

if #failures > 0 then
	for _, line in ipairs(failures) do print(line) end
	os.exit(1)
end
print(string.format("SMOKE OK [%s] %s: loaded, ADD_ON_LOADED, PLAYER_ACTIVATED, HUD shown, settings read, slash commands run, no unlisted globals, no cut-off text", mode, addon))
