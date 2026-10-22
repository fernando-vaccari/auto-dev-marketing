-- Auto Posts: câmera local em jogo autorizado. Não acessa disco, OBS ou senhas.
local RunService = game:GetService("RunService")
local StarterGui = game:GetService("StarterGui")
local Players = game:GetService("Players")
local Controller = {}
local running = false
local cancelled = false

local function resolve(path)
    local current = workspace
    for component in string.gmatch(path, "[^/]+") do
        current = current:FindFirstChild(component)
        if not current then error("Associe um objeto real ao caminho: " .. path) end
    end
    return current
end
local function position(object)
    if object:IsA("BasePart") then return object.Position end
    if object:IsA("Model") then return object:GetPivot().Position end
    error("O foco precisa ser uma BasePart ou Model real.")
end
function Controller.cancel()
    cancelled = true
end
function Controller.play(sequence)
    if running then return false, "Já existe uma sequência em execução." end
    local camera = workspace.CurrentCamera
    if not camera then return false, "Câmera indisponível." end
    -- Valida todos os pontos antes de ocultar interfaces ou iniciar o movimento.
    local ok, points = pcall(function()
        assert(type(sequence.points)=="table" and #sequence.points>=1, "Configure os pontos da sequência.")
        local found = {}
        for _, point in ipairs(sequence.points) do
            assert(type(point.duration)=="number" and point.duration>=0.1 and point.duration<=60, "Duração inválida.")
            local marker=resolve(point.camera)
            assert(marker:IsA("BasePart"), "O ponto de câmera deve ser BasePart.")
            local focus=point.focus and point.focus~="" and resolve(point.focus) or nil
            if focus then position(focus) end
            table.insert(found,{marker=marker,focus=focus,duration=point.duration,fov=math.clamp(point.fov or marker:GetAttribute("FOV") or 60,20,100),pan=point.pan or 0,cut=point.cut==true})
        end
        return found
    end)
    if not ok then return false, tostring(points) end
    running=true;cancelled=false
    local old={type=camera.CameraType,subject=camera.CameraSubject,cframe=camera.CFrame,fov=camera.FieldOfView}
    local enabled={}
    local playerGui=Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
    if sequence.hideUI and playerGui then
        for _, gui in ipairs(playerGui:GetChildren()) do
            if gui:IsA("ScreenGui") then enabled[gui]=gui.Enabled;gui.Enabled=false end
        end
    end
    local core={}
    if sequence.hideUI then
        for _, kind in ipairs(Enum.CoreGuiType:GetEnumItems()) do
            if kind~=Enum.CoreGuiType.All then
                local success,value=pcall(function() return StarterGui:GetCoreGuiEnabled(kind) end)
                if success then core[kind]=value;pcall(function() StarterGui:SetCoreGuiEnabled(kind,false) end) end
            end
        end
    end
    local success, message=pcall(function()
        camera.CameraType=Enum.CameraType.Scriptable
        for _, point in ipairs(points) do
            if cancelled then break end
            local start=camera.CFrame
            local fov=camera.FieldOfView
            if point.cut then start=point.marker.CFrame;fov=point.fov end
            local elapsed=0
            while elapsed<point.duration and not cancelled do
                elapsed+=RunService.RenderStepped:Wait()
                local alpha=math.clamp(elapsed/point.duration,0,1)
                local smooth=alpha*alpha*(3-2*alpha)
                local target=point.marker.CFrame*CFrame.Angles(0,math.rad(point.pan)*alpha,0)
                local value=start:Lerp(target,smooth)
                if point.focus then
                    local focusPosition=position(point.focus)
                    if (focusPosition-value.Position).Magnitude>0.001 then value=CFrame.lookAt(value.Position,focusPosition) end
                end
                camera.CFrame=value;camera.FieldOfView=fov+(point.fov-fov)*smooth
            end
        end
    end)
    camera.CFrame=old.cframe;camera.FieldOfView=old.fov
    camera.CameraSubject=old.subject;camera.CameraType=old.type
    for gui,value in pairs(enabled) do if gui.Parent then gui.Enabled=value end end
    for kind,value in pairs(core) do pcall(function() StarterGui:SetCoreGuiEnabled(kind,value) end) end
    running=false
    return success, message
end
return Controller
