-- Plugin local opcional: cria somente um marcador de câmera na posição atual.
local Selection=game:GetService("Selection")
local toolbar=plugin:CreateToolbar("Auto Posts")
local button=toolbar:CreateButton("Ponto de câmera","Criar marcador na câmera atual","")
button.Click:Connect(function()
    local camera=workspace.CurrentCamera
    if not camera then return end
    local folder=workspace:FindFirstChild("AutoPostsCameras")
    if not folder then folder=Instance.new("Folder");folder.Name="AutoPostsCameras";folder.Parent=workspace end
    local marker=Instance.new("Part")
    marker.Name="ponto_"..tostring(#folder:GetChildren()+1)
    marker.Anchored=true;marker.CanCollide=false;marker.CanTouch=false;marker.CanQuery=false
    marker.Transparency=0.75;marker.Size=Vector3.new(0.5,0.5,0.5);marker.CFrame=camera.CFrame
    marker:SetAttribute("FOV",camera.FieldOfView);marker.Parent=folder
    Selection:Set({marker})
end)
