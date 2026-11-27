param([Parameter(Mandatory = $true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$directory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $directory | Out-Null

$now = [DateTimeOffset]::UtcNow
$caKey = [System.Security.Cryptography.RSA]::Create(2048)
$caRequest = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
    'CN=Cogit A10 local test CA', $caKey,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256,
    [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
$caRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true, $false, 0, $true))
$caRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyCertSign -bor
        [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::CrlSign, $true))
$caRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509SubjectKeyIdentifierExtension]::new($caRequest.PublicKey, $false))
$ca = $caRequest.CreateSelfSigned($now.AddMinutes(-5), $now.AddDays(1))

$serverKey = [System.Security.Cryptography.RSA]::Create(2048)
$serverRequest = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
    'CN=host.docker.internal', $serverKey,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256,
    [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
$serverRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true))
$serverRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor
        [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment, $true))
$enhanced = [System.Security.Cryptography.OidCollection]::new()
[void]$enhanced.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
$serverRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($enhanced, $false))
$names = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$names.AddDnsName('host.docker.internal')
$serverRequest.CertificateExtensions.Add($names.Build())
$serverRequest.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509SubjectKeyIdentifierExtension]::new($serverRequest.PublicKey, $false))
$serial = [byte[]]::new(16)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($serial)
$serial[0] = $serial[0] -band 0x7f
$server = $serverRequest.Create($ca, $now.AddMinutes(-5), $now.AddHours(12), $serial)

[System.IO.File]::WriteAllText((Join-Path $directory 'ca.pem'), $ca.ExportCertificatePem())
[System.IO.File]::WriteAllText((Join-Path $directory 'server-cert.pem'), $server.ExportCertificatePem() + "`n" + $ca.ExportCertificatePem())
[System.IO.File]::WriteAllText((Join-Path $directory 'server-key.pem'), $serverKey.ExportPkcs8PrivateKeyPem())
Write-Output "Test CA SHA256 $((Get-FileHash -LiteralPath (Join-Path $directory 'ca.pem') -Algorithm SHA256).Hash.ToLowerInvariant())"
