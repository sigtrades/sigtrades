"""IBKR Web API 一键密钥生成。"""

from app.services.ibkr_web_keystore import generate_ibkr_oauth_materials


def test_generate_ibkr_oauth_materials_shape():
    data = generate_ibkr_oauth_materials()
    for key in (
        "signature_key_pem",
        "encryption_key_pem",
        "public_signature_pem",
        "public_encryption_pem",
        "dhparam_pem",
    ):
        assert key in data
        assert "BEGIN" in data[key]
    assert "PRIVATE" in data["signature_key_pem"]
    assert "PUBLIC" in data["public_signature_pem"]
    assert "DH PARAMETERS" in data["dhparam_pem"]
