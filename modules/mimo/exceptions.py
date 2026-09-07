"""MiMo 平台异常类"""


class OtpRequired(Exception):
    """需要 OTP 验证码"""


class PassTokenExpired(Exception):
    """passToken 过期"""


class LoginError(Exception):
    """登录过程中的通用错误"""


class StsError(Exception):
    """STS 换取 serviceToken 失败"""
