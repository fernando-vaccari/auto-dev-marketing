-- Mova este LocalScript para StarterPlayer/StarterPlayerScripts.
-- Mantenha CameraController e Sequences em ReplicatedStorage/AutoPostsCapture.
local UserInputService=game:GetService("UserInputService")
local package=game:GetService("ReplicatedStorage"):WaitForChild("AutoPostsCapture")
local controller=require(package:WaitForChild("CameraController"))
local sequences=require(package:WaitForChild("Sequences"))
local selected=1
UserInputService.InputBegan:Connect(function(input,processed)
    if processed then return end
    if input.KeyCode==Enum.KeyCode.F7 then
        selected=selected%#sequences+1
        print("Auto Posts: "..sequences[selected].name)
    elseif input.KeyCode==Enum.KeyCode.F8 then
        task.spawn(function()
            local success,message=controller.play(sequences[selected])
            if not success then warn("Auto Posts: "..tostring(message)) end
        end)
    elseif input.KeyCode==Enum.KeyCode.F9 then controller.cancel() end
end)
print("Auto Posts: F7 seleciona; F8 executa; F9 cancela. Sequências dependem de pontos reais configurados.")
