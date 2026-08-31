$path = "src/pages/RecommendPage.jsx"
$content = Get-Content -Raw -Path $path
$content = $content -replace 'buffer\.split\("`n`n"\)', 'buffer.split("\n\n")'
$content = $content -replace 'part\.trim\(\)\.split\("`n"\)', 'part.trim().split("\n")'
Set-Content -Path $path -Value $content -NoNewline
