# Standard library imports
import base64
import json
import os
import random
import re
import string
import uuid
import requests
from typing import Optional

# from urllib.parse import parse_qs, urlparse
try:
    from langdetect import detect
    from deep_translator import GoogleTranslator
    from google.cloud import translate_v2 as translate
except ImportError:
    pass
from bardapi.constants import (
    ALLOWED_LANGUAGES,
    REPLIT_SUPPORT_PROGRAM_LANGUAGES,
    SESSION_HEADERS,
    TEXT_GENERATION_WEB_SERVER_PARAM,
    Tool,
)
from bardapi.models.result import BardResult
from bardapi.utils import (
    build_bard_answer,
    build_export_data_structure,
    build_input_replit_data_struct,
    build_input_text_struct,
    extract_bard_cookie,
    upload_image,
)


class Bard:
    """
    Bard class for interacting with Google Bard.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: int = 20,
        proxies: Optional[dict] = None,
        session: Optional[requests.Session] = None,
        conversation_id: Optional[str] = None,
        google_translator_api_key: Optional[str] = None,
        language: Optional[str] = None,
        run_code: bool = False,
        token_from_browser: bool = False,
        multi_cookies_bool: bool = False,
        cookie_dict: dict = None,
    ):
        """
        Initialize the Bard instance.

        Args:
            token (str, optional): Bard API token.
            timeout (int, optional, default = 20): Request timeout in seconds.
            proxies (dict, optional): Proxy configuration for requests.
            session (requests.Session, optional): Requests session object.
            conversation_id (str, optional): ID for fetching conversational context.
            google_translator_api_key (str, optional): Google Cloud Translation API key.
            language (str, optional): Natural language code for translation (e.g., "en", "ko", "ja").
            run_code (bool, optional, default = False): Whether to directly execute the code included in the answer (IPython only).
            token_from_browser (bool, optional, default = False): Retrieve a token from the browser.
            multi_cookies_bool: When using token_from_browser, automatically extract 3 cookies (__Secure-1PSID, __Secure-1PSIDTS, __Secure-1PSIDCC).
            cookie_dict: Pass 3 cookies (__Secure-1PSID, __Secure-1PSIDTS, __Secure-1PSIDCC) as keys with their respective values.
        """
        self.cookie_dict = cookie_dict
        self.multi_cookies_bool = multi_cookies_bool
        self.token = self._get_token(token, token_from_browser, multi_cookies_bool)
        self.proxies = proxies
        self.timeout = timeout
        self._reqid = int("".join(random.choices(string.digits, k=4)))
        self.conversation_id = conversation_id or ""
        self.response_id = ""
        self.choice_id = ""
        self.session = self._get_session(session)
        self.SNlM0e = self._get_snim0e()
        self.language = language or os.getenv("_BARD_API_LANG")
        self.run_code = run_code
        self.google_translator_api_key = google_translator_api_key
        self.og_pid = ""
        self.rot = ""
        self.exp_id = ""
        self.init_value = ""

        if google_translator_api_key:
            assert translate

    def _get_token(
        self, token: str, token_from_browser: bool, multi_cookies_bool: bool
    ) -> str:
        """
        Get the Bard API token either from the provided token or from the browser cookie.

        Args:
            token (str): Bard API token.
            token_from_browser (bool): Whether to extract the token from the browser cookie.
            multi_cookies_bool (bool): Whether to extract multiple cookies from the browser.

        Returns:
            str: The Bard API token.
        Raises:
            Exception: If the token is not provided and can't be extracted from the browser.
        """
        if token:
            return token

        env_token = os.getenv("_BARD_API_KEY")
        if env_token:
            return env_token

        if token_from_browser:
            extracted_cookie_dict = extract_bard_cookie(cookies=multi_cookies_bool)
            if self.multi_cookies_bool:
                self.cookie_dict = extracted_cookie_dict
                required_cookies = [
                    "__Secure-1PSID",
                    "__Secure-1PSIDTS",
                    "__Secure-1PSIDCC",
                    "NID",
                ]
                if len(extracted_cookie_dict) < len(required_cookies) or not all(
                    key in extracted_cookie_dict for key in required_cookies
                ):
                    print(
                        "Essential cookies (__Secure-1PSID, __Secure-1PSIDTS, __Secure-1PSIDCC) are missing."
                    )
                    return extracted_cookie_dict.get("__Secure-1PSID", "")
            if extracted_cookie_dict:
                return extracted_cookie_dict.get("__Secure-1PSID", "")

        raise Exception(
            "Bard API Key must be provided as the 'token' argument or extracted from the browser."
        )

    def _get_session(self, session: Optional[requests.Session]) -> requests.Session:
        """
        Get the requests Session object.

        Args:
            session (requests.Session): Requests session object.

        Returns:
            requests.Session: The Session object.
        """
        if session is not None:
            return session

        new_session = requests.Session()
        new_session.headers = SESSION_HEADERS
        new_session.cookies.set("__Secure-1PSID", self.token)
        new_session.proxies = self.proxies

        if self.cookie_dict is not None:
            for k, v in self.cookie_dict.items():
                new_session.cookies.set(k, v)

        return new_session

    def _get_snim0e(self) -> str:
        """
        Get the SNlM0e value from the Bard API response.

        Returns:
            str: SNlM0e value.
        Raises:
            Exception: If the __Secure-1PSID value is invalid or SNlM0e value is not found in the response.
        """
        response = self.session.get(
            "https://gemini.google.com/", timeout=self.timeout, proxies=self.proxies
        )
        if response.status_code != 200:
            raise Exception(
                f"Response status code is not 200. Response Status is {response.status_code}"
            )
        snim0e = re.findall(r'nonce="([^"]+)"', response.text)
        if snim0e == None:
            raise Exception(
                "SNlM0e token value not found. Double-check cookies dict value or set 'auto_cookies' parametes as True.\nOccurs due to cookie changes. Re-enter new cookie, restart browser, re-login, or manually refresh cookie."
            )
        return snim0e

    def get_answer(
        self,
        input_text: str,
        image: Optional[bytes] = None,
        image_name: Optional[str] = None,
        tool: Optional[Tool] = None,
    ) -> dict:
        """
        Get an answer from the Bard API for the given input text.

        Example:
        >>> token = 'xxxxxx'
        >>> bard = Bard(token=token)

        >>> response = bard.get_answer("나와 내 동년배들이 좋아하는 뉴진스에 대해서 알려줘")
        >>> print(response['content'])

        Args:
            input_text (str): Input text for the query.
            image (bytes): Input image bytes for the query, support image types: jpeg, png, webp
            image_name (str): Short file name
            tool : tool to use can be one of Gmail, Google Docs, Google Drive, Google Flights, Google Hotels, Google Maps, Youtube

        Returns:
            dict: Answer from the Bard API in the following format:
                {
                    "content": str,
                    "conversation_id": str,
                    "response_id": str,
                    "factuality_queries": list,
                    "text_query": str,
                    "choices": list,
                    "links": list,
                    "images": list,
                    "program_lang": str,
                    "code": str,
                    "status_code": int
                }
        """
        params = {
            "bl": TEXT_GENERATION_WEB_SERVER_PARAM,
            "_reqid": str(self._reqid),
            "rt": "c",
        }
        if self.google_translator_api_key is not None:
            google_official_translator = translate.Client(
                api_key=self.google_translator_api_key
            )

        # [Optional] Language translation
        if (
            self.language is not None
            and self.language not in ALLOWED_LANGUAGES
            and self.google_translator_api_key is None
        ):
            translator_to_eng = GoogleTranslator(source="auto", target="en")
            input_text = translator_to_eng.translate(input_text)
        elif (
            self.language is not None
            and self.language not in ALLOWED_LANGUAGES
            and self.google_translator_api_key is not None
        ):
            input_text = google_official_translator.translate(
                input_text, target_language="en"
            )

        if image is not None:
            image_url = upload_image(image)
        else:
            image_url = None

        # Make post data structure and insert prompt
        input_text_struct = build_input_text_struct(
            input_text,
            self.conversation_id,
            self.response_id,
            self.choice_id,
            image_url,
            image_name,
            tools=[tool.value] if tool is not None else None,
        )

        data = {
            "f.req": json.dumps([None, json.dumps(input_text_struct)]),
            "at": self.SNlM0e,
        }

        # Get response
        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
            params=params,
            data=data,
            timeout=self.timeout,
            proxies=self.proxies,
        )

        # Post-processing of response
        resp_dict = json.loads(resp.content.splitlines()[-5])[0][2]

        if not resp_dict:
            return {
                "content": f"Response Error: {resp.content}. "
                f"\nUnable to get response."
                f"\nPlease double-check the cookie values and verify your network environment or google account."
            }
        resp_json = json.loads(resp_dict)
        if resp_json[4] is None:
            resp_dict = json.loads(resp.content.splitlines()[-7])[0][2]
            resp_json = json.loads(resp_dict)

        # [Optional] Gather image links
        images = list()
        try:
            if len(resp_json) >= 3:
                nested_list = resp_json[4][0][4]
                for img in nested_list:
                    images.append(img[0][0][0])
        except (IndexError, TypeError, KeyError):
            pass

        # Parsed Answer Object
        parsed_answer = json.loads(resp_dict)

        # [Optional] Translated by google translator
        # Unofficial
        if self.language is not None and self.language not in ALLOWED_LANGUAGES:
            if self.google_translator_api_key is None:
                translator_func = GoogleTranslator(
                    source="auto", target=self.language
                ).translate
            else:

                def translator_func(text):
                    return google_official_translator(
                        text, target_language=self.language
                    )

            parsed_answer[4] = [
                [x[0], [translator_func(x[1][0])] + x[1][1:], x[2]]
                for x in parsed_answer[4]
            ]

        # [Optional] Get program_lang & code
        try:
            program_lang = (
                parsed_answer[4][0][1][0].split("```")[1].split("\n")[0].strip()
            )
            code = parsed_answer[4][0][1][0].split("```")[1][len(program_lang) :]
        except Exception:
            program_lang, code = None, None

        # Returns dictionary object
        bard_answer = build_bard_answer(
            parsed_answer, images, program_lang, code, resp.status_code
        )

        # Update params
        self.conversation_id, self.response_id, self.choice_id = (
            bard_answer["conversation_id"],
            bard_answer["response_id"],
            bard_answer["choices"][0]["id"],
        )
        self._reqid += 100000

        # [Optional] Execute code
        if self.run_code and bard_answer["code"] is not None:
            try:
                print(bard_answer["code"])
                exec(bard_answer["code"])
            except Exception:
                pass

        return bard_answer

    def speech(self, input_text: str, lang: str = "en-US") -> dict:
        """
        Get speech audio from Bard API for the given input text.

        Example:
        >>> token = 'xxxxxx'
        >>> bard = Bard(token=token)
        >>> audio = bard.speech("hello!")
        >>> with open("bard.ogg", "wb") as f:
        >>>     f.write(bytes(audio['audio']))

        Args:
            input_text (str): Input text for the query.
            lang (str, optional, default = "en-US"): Input language for the query.

        Returns:
            dict: Answer from the Bard API in the following format:
            {
                "audio": bytes,
                "status_code": int
            }
        """
        params = {
            "bl": TEXT_GENERATION_WEB_SERVER_PARAM,
            "_reqid": str(self._reqid),
            "rt": "c",
        }

        input_text_struct = [
            [["XqA3Ic", json.dumps([None, input_text, lang, None, 2])]]
        ]

        data = {
            "f.req": json.dumps(input_text_struct),
            "at": self.SNlM0e,
        }

        # Get response
        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/batchexecute",
            params=params,
            data=data,
            timeout=self.timeout,
            proxies=self.proxies,
        )

        # Post-processing of response
        resp_dict = json.loads(resp.content.splitlines()[3])[0][2]
        if not resp_dict:
            return {
                "content": f"Response Error: {resp.content}. "
                f"\nUnable to get response."
                f"\nPlease double-check the cookie values and verify your network environment or google account."
            }
        resp_json = json.loads(resp_dict)
        audio_b64 = resp_json[0]
        audio_bytes = base64.b64decode(audio_b64)
        return {"audio": audio_bytes, "status_code": resp.status_code}

    def export_conversation(self, bard_answer, title: str = "") -> dict:
        """
        Get Share URL for specific answer from bard

        Example:
        >>> token = 'xxxxxx'
        >>> bard = Bard(token=token)
        >>> bard_answer = bard.get_answer("hello!")
        >>> url = bard.export_conversation(bard_answer, title="Export Conversation")
        >>> print(url['url'])

        Args:
            bard_answer (dict): bard_answer returned from get_answer
            title (str, optional, default = ""): Title for URL
        Returns:
            dict: Answer from the Bard API in the following format:
            {
                "url": str,
                "status_code": int
            }
        """
        conv_id = bard_answer["conversation_id"]
        resp_id = bard_answer["response_id"]
        choice_id = bard_answer["choices"][0]["id"]
        params = {
            "rpcids": "fuVx7",
            "source-path": "/",
            "bl": TEXT_GENERATION_WEB_SERVER_PARAM,
            "rt": "c",
        }

        # Build data structure
        export_data_structure = build_export_data_structure(
            conv_id, resp_id, choice_id, title
        )

        data = {
            "f.req": json.dumps(export_data_structure),
            "at": self.SNlM0e,
        }
        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/batchexecute",
            params=params,
            data=data,
            timeout=self.timeout,
            proxies=self.proxies,
        )

        # Post-processing of response
        resp_dict = json.loads(resp.content.splitlines()[3])
        url_id = json.loads(resp_dict[0][2])[2]
        url = f"https://g.co/bard/share/{url_id}"

        # Increment request ID
        self._reqid += 100000
        return {"url": url, "status_code": resp.status_code}

    def ask_about_image(
        self, input_text: str, image: bytes, lang: Optional[str] = None
    ) -> dict:
        """
        Send Bard image along with question and get answer

        Example:
        >>> token = 'xxxxxx'
        >>> bard = Bard(token=token)
        >>> image = open('image.jpg', 'rb').read()
        >>> bard_answer = bard.ask_about_image("what is in the image?", image)['content']

        Args:
            input_text (str): Input text for the query.
            image (bytes): Input image bytes for the query, support image types: jpeg, png, webp
            lang (str, optional): Language to use.

        Returns:
            dict: Answer from the Bard API in the following format:
                {
                    "content": str,
                    "conversation_id": str,
                    "response_id": str,
                    "factuality_queries": list,
                    "text_query": str,
                    "choices": list,
                    "links": list,
                    "images": list,
                    "program_lang": str,
                    "code": str,
                    "status_code": int
                }
        """
        if self.google_translator_api_key is not None:
            google_official_translator = translate.Client(
                api_key=self.google_translator_api_key
            )
        elif self.language is not None or lang is not None:
            translator_to_eng = GoogleTranslator(source="auto", target="en")

        # [Optional] Set language
        if self.language is None and lang is None:
            translated_input_text = input_text
        elif (
            (self.language is not None or lang is not None)
            and self.language not in ALLOWED_LANGUAGES
            and self.google_translator_api_key is None
        ):
            translator_to_eng = GoogleTranslator(source="auto", target="en")
            translated_input_text = translator_to_eng.translate(input_text)
        elif (
            (self.language is not None or lang is not None)
            and self.language not in ALLOWED_LANGUAGES
            and self.google_translator_api_key is not None
        ):
            translated_input_text = google_official_translator.translate(
                input_text, target_language="en"
            )
        elif (
            (self.language is None or lang is None)
            and self.language not in ALLOWED_LANGUAGES
            and self.google_translator_api_key is None
        ):
            translator_to_eng = GoogleTranslator(source="auto", target="en")
            translated_input_text = translator_to_eng.translate(input_text)

        # Supported format: jpeg, png, webp
        image_url = upload_image(image)

        input_data_struct = [
            None,
            [
                [
                    translated_input_text,
                    0,
                    None,
                    [[[image_url, 1], "uploaded_photo.jpg"]],
                ],
                [lang if lang is not None else self.language],
                ["", "", ""],
                "",  # Unknown random string value (1000 characters +)
                uuid.uuid4().hex,  # Should be random uuidv4 (32 characters)
                None,
                [1],
                0,
                [],
                [],
            ],
        ]
        params = {
            "bl": "boq_assistant-bard-web-server_20230716.16_p2",
            "_reqid": str(self._reqid),
            "rt": "c",
        }
        input_data_struct[1] = json.dumps(input_data_struct[1])
        data = {
            "f.req": json.dumps(input_data_struct),
            "at": self.SNlM0e,
        }

        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
            params=params,
            data=data,
            timeout=self.timeout,
            proxies=self.proxies,
        )

        # Post-processing of response
        resp_dict = json.loads(resp.content.splitlines()[3])[0][2]
        if not resp_dict:
            return {
                "content": f"Response Error: {resp.content}. "
                f"\nUnable to get response."
                f"\nPlease double-check the cookie values and verify your network environment or google account."
            }
        parsed_answer = json.loads(resp_dict)
        content = parsed_answer[4][0][1][0]
        try:
            if self.language is None and self.google_translator_api_key is None:
                translated_content = content
            elif self.language is not None and self.google_translator_api_key is None:
                translator = GoogleTranslator(source="en", target=self.language)
                translated_content = translator.translate(content)

            elif lang is not None and self.google_translator_api_key is None:
                translator = GoogleTranslator(source="en", target=lang)
                translated_content = translator.translate(content)

            elif (
                lang is None and self.language is None
            ) and self.google_translator_api_key is None:
                us_lang = detect(input_text)
                translator = GoogleTranslator(source="en", target=us_lang)
                translated_content = translator.translate(content)

            elif (
                self.language is not None and self.google_translator_api_key is not None
            ):
                translated_content = google_official_translator.translate(
                    content, target_language=self.language
                )
            elif lang is not None and self.google_translator_api_key is not None:
                translated_content = google_official_translator.translate(
                    content, target_language=lang
                )
            elif (
                self.language is None and lang is None
            ) and self.google_translator_api_key is not None:
                us_lang = detect(input_text)
                translated_content = google_official_translator.translate(
                    content, target_language=us_lang
                )
        except Exception as e:
            print(f"Translation failed, and the original text has been returned. \n{e}")
            translated_content = content

        # Returned dictionary object
        bard_answer = {
            "content": translated_content,
            "conversation_id": parsed_answer[1][0],
            "response_id": parsed_answer[1][1],
            "factuality_queries": parsed_answer[3],
            "text_query": parsed_answer[2][0] if parsed_answer[2] else "",
            "choices": [{"id": x[0], "content": x[1]} for x in parsed_answer[4]],
            "links": self._extract_links(parsed_answer[4]),
            "images": [""],
            "program_lang": "",
            "code": "",
            "status_code": resp.status_code,
        }
        self.conversation_id, self.response_id, self.choice_id = (
            bard_answer["conversation_id"],
            bard_answer["response_id"],
            bard_answer["choices"][0]["id"],
        )
        self._reqid += 100000
        return bard_answer

    def ask(
        self,
        text: str,
        image: Optional[bytes] = None,
        image_name: Optional[str] = None,
        tool: Optional[Tool] = None,
    ) -> BardResult:
        if image is not None:
            image_url = upload_image(image)
        else:
            image_url = None

        # Make post data structure and insert prompt
        input_text_struct = build_input_text_struct(
            text,
            self.conversation_id,
            self.response_id,
            self.choice_id,
            image_url,
            image_name,
            tools=[tool.value] if tool is not None else None,
        )

        # Get response
        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
            params={
                "bl": TEXT_GENERATION_WEB_SERVER_PARAM,
                "_reqid": str(self._reqid),
                "rt": "c",
            },
            data={
                "f.req": json.dumps([None, json.dumps(input_text_struct)]),
                "at": self.SNlM0e,
            },
            timeout=self.timeout,
            proxies=self.proxies,
        )

        if resp.status_code != 200:
            raise Exception(
                f"Response status code is not 200. Response Status is {resp.status_code}"
            )

        lines = [
            line for line in resp.content.splitlines() if line.startswith(b'[["wrb.fr')
        ]
        jsons = [json.loads(json.loads(line)[0][2]) for line in lines]
        # Post-processing of response
        resp_json = jsons[-1]

        if not resp_json:
            raise {
                "content": f"Response Error: {resp.content}. "
                f"\nUnable to get response."
                f"\nPlease double-check the cookie values and verify your network environment or google account."
            }

        res = BardResult(resp_json)
        if not res.drafts:
            res = BardResult(jsons[-2])

        # Update params
        self.conversation_id, self.response_id, self.choice_id = (
            res.conversation_id,
            res.response_id,
            res.drafts[0].id,
        )
        self._reqid += 100000

        return res

    def export_replit(
        self,
        code: str,
        program_lang: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        Get export URL to repl.it from code

        Example:
        >>> token = 'xxxxxx'
        >>> bard = Bard(token=token)
        >>> bard_answer = bard.get_answer("Give me python code to print hello world")
        >>> url = bard.export_replit(bard_answer['code'], bard_answer['program_lang'])
        >>> print(url['url'])

        Args:
            code (str): source code
            program_lang (str, optional): programming language
            filename (str, optional): filename
            **kwargs: instructions, source_path
        Returns:
        dict: Answer from the Bard API in the following format:
            {
                "url": str,
                "status_code": int
            }
        """
        params = {
            "rpcids": "qACoKe",
            "source-path": kwargs.get("source_path", "/"),
            "bl": TEXT_GENERATION_WEB_SERVER_PARAM,
            "_reqid": str(self._reqid),
            "rt": "c",
        }

        # Reference: https://github.com/jincheng9/markdown_supported_languages
        if program_lang not in REPLIT_SUPPORT_PROGRAM_LANGUAGES and filename is None:
            raise Exception(
                f"Language {program_lang} not supported, please set filename manually."
            )

        filename = (
            REPLIT_SUPPORT_PROGRAM_LANGUAGES.get(program_lang, filename)
            if filename is None
            else filename
        )
        input_replit_data_struct = build_input_replit_data_struct(
            kwargs.get("instructions", ""), code, filename
        )

        data = {
            "f.req": json.dumps(input_replit_data_struct),
            "at": self.SNlM0e,
        }

        # Get response
        resp = self.session.post(
            "https://gemini.google.com/_/BardChatUi/data/batchexecute",
            params=params,
            data=data,
            timeout=self.timeout,
            proxies=self.proxies,
        )

        resp_dict = json.loads(resp.content.splitlines()[3])
        print(f"Response: {resp_dict}")

        url = json.loads(resp_dict[0][2])[0]

        # Increment request ID
        self._reqid += 100000

        return {"url": url, "status_code": resp.status_code}

    def _extract_links(self, data: list) -> list:
        """
        Extract links from the given data.

        Args:
            data: Data to extract links from.

        Returns:
            list: Extracted links.
        """
        links = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, list):
                    links.extend(self._extract_links(item))
                elif (
                    isinstance(item, str)
                    and item.startswith("http")
                    and "favicon" not in item
                ):
                    links.append(item)
        return links

    # def _set_cookie_refresh_data(self):
    #     resp = self.session.get(
    #         "https://gemini.google.com/", timeout=self.timeout, proxies=self.proxies
    #     )

    #     og_pid_regex = r"https:\/\/accounts\.google\.com\/ListAccounts\?authuser=[0-9]+\\u0026pid=([0-9]+)"
    #     exp_id_regex = r'https:\/\/accounts\.google\.com\/RotateCookiesPage"],([0-9]+,[0-9]+,[0-9]+,[0-9]+,[0-9]+,[0-9]+)'

    #     matches_og_pid = re.search(og_pid_regex, resp.text)
    #     matches_exp_id = re.search(exp_id_regex, resp.text)

    #     print(matches_og_pid, matches_exp_id)
    #     if matches_og_pid:
    #         og_pid_url = matches_og_pid.group(0)
    #         og_pid_query = urlparse(og_pid_url.replace("\\u0026", "&")).query
    #         print(og_pid_query)
    #         og_pid = parse_qs(og_pid_query)["pid"][0]
    #         print(f"og_pid: {og_pid}")
    #         self.og_pid = og_pid

    #     if matches_exp_id:
    #         values_str = matches_exp_id.group(1)
    #         values_array = [int(val) for val in values_str.split(",")]
    #         print(f"Values array: {values_array}")

    #         if len(values_array) >= 5:
    #             rot = values_array[0]
    #             exp_id = values_array[4]

    #             # You can print or use rot and exp_id as needed
    #             print(f"rot: {rot}")
    #             print(f"exp_id: {exp_id}")

    #             self.rot = rot
    #             self.exp_id = exp_id

    #         # Update cookies using the extracted og_pid and exp_id
    #         update_cookies_url = f"https://accounts.google.com/RotateCookiesPage?og_pid={self.og_pid}&rot={self.rot}&origin=https%3A%2F%2Fbard.google.com&exp_id={self.exp_id}"
    #         headers_google = {
    #             "Host": "accounts.google.com",
    #             "Referer": "https://gemini.google.com/",
    #             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    #         }

    #         try:
    #             response = self.session.get(
    #                 update_cookies_url,
    #                 headers=headers_google,
    #                 timeout=self.timeout,
    #                 proxies=self.proxies,
    #             )
    #             response.raise_for_status()
    #         except requests.exceptions.HTTPError as err:
    #             print(f"HTTP Error: {err}")
    #         # Extract initValue from the updated cookies
    #         print(response.text)
    #         init_value_regex = r"init\(\'(-?\d+)\',"
    #         matches_init_value = re.findall(init_value_regex, response.text)
    #         print(matches_init_value)
    #         if matches_init_value:
    #             self.init_value = matches_init_value[0]

    # def update_1PSIDTS(self):
    #     # Prepare request data
    #     self._set_cookie_refresh_data()
    #     data = [self.og_pid, f"{self.init_value}"]
    #     data = json.dumps(data)
    #     update_cookies_url = f"https://accounts.google.com/RotateCookiesPage?og_pid={self.og_pid}&rot={self.rot}&origin=https%3A%2F%2Fbard.google.com&exp_id={self.exp_id}"

    #     # Update 1PSIDTS using the extracted og_pid and initValue
    #     update_1psidts_url = "https://accounts.google.com/RotateCookies"
    #     headers_rotate = {
    #         "Host": "accounts.google.com",
    #         "Content-Type": "application/json",
    #         "Referer": update_cookies_url,
    #         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    #     }
    #     # headers_rotate.update(self.headers)

    #     response = self.session.post(
    #         update_1psidts_url,
    #         data=data,
    #         headers=headers_rotate,
    #         timeout=self.timeout,
    #         proxies=self.proxies,
    #     )
    #     response.raise_for_status()

    #     # Extract updated 1PSIDTS from the response headers
    #     cookie_headers = response.headers.get("Set-Cookie", "")
    #     parsed_cookies = self.parse_cookies(cookie_headers)
    #     return parsed_cookies

    # def parse_cookies(self, cookie_headers):
    #     cookie_dict = {}

    #     matches = re.findall(r"([^;]+)", cookie_headers)

    #     for match in matches:
    #         key_value = match.split("=")
    #         if len(key_value) == 2:
    #             cookie_dict[key_value[0].strip()] = key_value[1].strip()

    #     return cookie_dict
