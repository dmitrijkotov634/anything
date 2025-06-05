import hashlib
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


def _get_function_signature(func: Callable) -> str:
    # noinspection PyUnresolvedReferences
    annotations = func.__annotations__.copy()
    return_type = annotations.pop("return", "None")
    return f"Function: {func.__name__}, Doc: {func.__doc__}, Args: {annotations}, Return: {return_type}"


def _get_cache_key(func_name: str, args, kwargs) -> str:
    arg_types = [type(arg).__name__ for arg in args]
    kwarg_types = {k: type(v).__name__ for k, v in kwargs.items()}
    return f"{func_name}_{arg_types}_{kwarg_types}"


def _clean_code(content: str) -> str:
    if content.startswith("```python"):
        content = content[9:-3]
    elif content.startswith("```"):
        content = content[3:-3]
    return content.strip()


def _save_to_cache(cache_path: Path, code: str):
    with cache_path.open("w") as f:
        f.write(code)


class BaseGenerator:
    def __init__(
            self,
            api_key: Optional[str] = None,
            cache_dir: Path = Path(".") / ".anything",
            env: Optional[dict] = None,
            model: str = "gpt-4.1-nano"
    ):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self._env = env or {}
        self.model = model

    def _get_cache_path(self, id_: str, cache_key: str) -> Path:
        hash_key = hashlib.sha256(cache_key.encode()).hexdigest()
        return self.cache_dir / f"{id_}_{hash_key}.py"

    def _load_from_cache(self, cache_path: Path, func_name: str) -> Optional[Callable]:
        if cache_path.exists():
            logger.info(f"Loading function '{func_name}' from cache: {cache_path}")
            with cache_path.open("r") as f:
                code = f.read()
            exec(code, self._env)
            return self._env.get(func_name)
        logger.debug(f"Cache miss for function '{func_name}': {cache_path}")
        return None

    def _generate_code(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug(f"Generating code for: {user_prompt}")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            content = response.choices[0].message.content
            logger.debug(f"Received response from OpenAI, length: {len(content)} chars")
            return _clean_code(content)
        except Exception as e:
            logger.error(f"Failed to generate code: {e}")
            raise

    def _execute_code(self, code: str, func_name: str) -> Callable:
        try:
            exec(code, self._env)
            logger.debug(f"Code executed successfully for '{func_name}'")
            return self._env[func_name]
        except Exception as e:
            logger.error(f"Failed to execute generated code for '{func_name}': {e}")
            raise


class Anything(BaseGenerator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._system_prompt = (
            "Generate Python function code based on function signature and docstring. "
            "Return only the function implementation without explanations or function calls."
        )

    def __call__(self, func: Callable, context: str = "") -> Callable:
        signature = _get_function_signature(func)
        cache_key = signature + context
        cache_path = self._get_cache_path(func.__name__, cache_key)

        logger.debug(f"Processing function '{func.__name__}'")

        cached_func = self._load_from_cache(cache_path, func.__name__)
        if cached_func:
            return cached_func

        user_prompt = signature
        if context:
            user_prompt = f"Context of related functions:\n{context}\n\nGenerate code for:\n{signature}"

        code = self._generate_code(self._system_prompt, user_prompt)
        logger.info(f"Successfully generated code for '{func.__name__}'")

        func_impl = self._execute_code(code, func.__name__)
        _save_to_cache(cache_path, code)
        return func_impl


class LazyAnything:
    def __init__(self, **kwargs):
        self.generator = Anything(**kwargs)
        self._registered_functions = {}
        self._pending_functions = {}
        self._generated = False

    def register(self, func: Callable) -> Callable:
        logger.debug(f"Registering lazy function: {func.__name__}")
        self._pending_functions[func.__name__] = func

        def wrapper(*args, **kwargs):
            if not self._generated:
                self._generate_all()
            return self._registered_functions[func.__name__](*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        # noinspection PyUnresolvedReferences
        wrapper.__annotations__ = func.__annotations__
        return wrapper

    def _build_context(self) -> str:
        context_parts = []
        for name, func in self._pending_functions.items():
            signature = _get_function_signature(func)
            context_parts.append(signature)
        return "\n".join(context_parts)

    def _generate_all(self):
        if self._generated:
            return

        logger.info(f"Generating all {len(self._pending_functions)} registered functions")
        context = self._build_context()

        for name, func in self._pending_functions.items():
            logger.info(f"Generating function '{name}' with full context")
            self._registered_functions[name] = self.generator(func, context)

        self._generated = True
        logger.info("All functions generated successfully")

    def generate_all(self):
        self._generate_all()

    def finalize(self):
        self._generate_all()


class Everything(BaseGenerator):
    def __init__(self, **kwargs):
        super().__init__(cache_dir=kwargs.get('cache_dir', Path(".") / ".everything"), **kwargs)
        self._functions = {}
        self._constants = {}
        self._context = []
        self._system_prompt = (
            "Generate Python function implementation based on function name and argument types. "
            "Return only the function code without explanations."
        )
        self._constant_prompt = (
            "Generate a Python constant value based on the constant name. "
            "Return only the value assignment without explanations. "
            "Format: CONSTANT_NAME = value"
        )

    def _get_context_string(self) -> str:
        if not self._context:
            return ""
        return "Previously generated context:\n" + "\n".join(self._context) + "\n\n"

    def _add_to_context(self, item_type: str, name: str, description: str):
        context_entry = f"{item_type}: {name} - {description}"
        if context_entry not in self._context:
            self._context.append(context_entry)

    def _generate_function(self, func_name: str, args, kwargs) -> Callable:
        cache_key = _get_cache_key(func_name, args, kwargs)
        cache_path = self._get_cache_path(func_name, cache_key)

        cached_func = self._load_from_cache(cache_path, func_name)
        if cached_func:
            arg_types = [type(arg).__name__ for arg in args]
            kwarg_types = {k: type(v).__name__ for k, v in kwargs.items()}
            self._add_to_context("Function", func_name, f"args: {arg_types}, kwargs: {kwarg_types}")
            return cached_func

        arg_types = [type(arg).__name__ for arg in args]
        kwarg_types = {k: type(v).__name__ for k, v in kwargs.items()}

        context_string = self._get_context_string()
        user_prompt = f"{context_string}Function name: {func_name}, argument types: args: {arg_types}"
        if kwarg_types:
            user_prompt += f", kwargs: {kwarg_types}"

        code = self._generate_code(self._system_prompt, user_prompt)
        func_impl = self._execute_code(code, func_name)
        _save_to_cache(cache_path, code)

        self._add_to_context("Function", func_name, f"args: {arg_types}, kwargs: {kwarg_types}")
        return func_impl

    def _generate_constant(self, const_name: str):
        cache_key = f"const_{const_name}"
        cache_path = self._get_cache_path(const_name, cache_key)

        if cache_path.exists():
            with cache_path.open("r") as f:
                code = f.read()
            local_env = {}
            exec(code, local_env)
            value = local_env.get(const_name, local_env.get(const_name.upper()))
            self._add_to_context("Constant", const_name, f"value: {value}")
            return value

        context_string = self._get_context_string()
        user_prompt = f"{context_string}Constant name: {const_name}"

        code = self._generate_code(self._constant_prompt, user_prompt)
        _save_to_cache(cache_path, code)

        local_env = {}
        exec(code, local_env, local_env)
        value = local_env.get(const_name, local_env.get(const_name.upper()))

        self._add_to_context("Constant", const_name, f"value: {value}")
        return value

    def __getattr__(self, func_name: str) -> Callable:
        def wrapper(*args, **kwargs):
            cache_key = _get_cache_key(func_name, args, kwargs)

            if cache_key not in self._functions:
                self._functions[cache_key] = self._generate_function(func_name, args, kwargs)

            return self._functions[cache_key](*args, **kwargs)

        return wrapper

    def __getitem__(self, const_name: str):
        if const_name not in self._constants:
            self._constants[const_name] = self._generate_constant(const_name)
        return self._constants[const_name]

    def get_context(self) -> list:
        return self._context.copy()

    def clear_context(self):
        self._context.clear()
