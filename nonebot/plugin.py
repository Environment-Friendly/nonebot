import os
import re
import sys
import shlex
import warnings
import importlib
import contextlib
from datetime import timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any, List, Set, Dict, Tuple, TypeVar, Union, Optional, Iterable, Callable, Type, overload

from .log import logger
from nonebot import permission as perm
from .command import Command, CommandManager, CommandSession
from .notice_request import EventHandler, EventManager
from .natural_language import NLProcessor, NLPManager
from .typing import CommandName_T, CommandHandler_T, NLPHandler_T, NoticeHandler_T, Patterns_T, PermissionPolicy_T, RequestHandler_T

if TYPE_CHECKING:
    from .message import MessagePreprocessor


class Plugin:
    __slots__ = ('module', 'name', 'usage', 'userdata', 'commands', 'nl_processors',
                 'event_handlers', 'msg_preprocessors')

    def __init__(self,
                 module: ModuleType,
                 name: Optional[str] = None,
                 usage: Optional[Any] = None,
                 userdata: Optional[Any] = None,
                 commands: Set[Command] = ...,
                 nl_processors: Set[NLProcessor] = ...,
                 event_handlers: Set[EventHandler] = ...,
                 msg_preprocessors: Set['MessagePreprocessor'] = ...):
        """Creates a plugin with no name, no usage, and no handlers."""

        self.module = module
        self.name = name
        self.usage = usage
        self.userdata = userdata
        self.commands: Set[Command] = \
            commands if commands is not ... else set()
        self.nl_processors: Set[NLProcessor] = \
            nl_processors if nl_processors is not ... else set()
        self.event_handlers: Set[EventHandler] = \
            event_handlers if event_handlers is not ... else set()
        self.msg_preprocessors: Set['MessagePreprocessor'] = \
            msg_preprocessors if msg_preprocessors is not ... else set()

    class GlobalTemp:
        """INTERNAL API"""

        # command, aliases, pattern
        commands: List[Tuple[Command, Union[Iterable[str], str], Patterns_T]] = []
        nl_processors: Set[NLProcessor] = set()
        event_handlers: Set[EventHandler] = set()
        msg_preprocessors: Set['MessagePreprocessor'] = set()
        now_within_plugin: bool = False

        @classmethod
        @contextlib.contextmanager
        def enter_plugin(cls):
            try:
                cls.clear()
                cls.now_within_plugin = True
                yield
            finally:
                cls.now_within_plugin = False

        @classmethod
        def clear(cls):
            cls.commands.clear()
            cls.nl_processors.clear()
            cls.event_handlers.clear()
            cls.msg_preprocessors.clear()

        @classmethod
        def make_plugin(cls, module: ModuleType):
            return Plugin(module=module,
                          name=getattr(module, '__plugin_name__', None),
                          usage=getattr(module, '__plugin_usage__', None),
                          userdata=getattr(module, '__plugin_userdata__', None),
                          commands={cmd[0] for cmd in cls.commands},
                          nl_processors={*cls.nl_processors},
                          event_handlers={*cls.event_handlers},
                          msg_preprocessors={*cls.msg_preprocessors})


class PluginManager:
    _plugins: Dict[str, Plugin] = {}

    def __init__(self):
        self.cmd_manager = CommandManager()
        self.nlp_manager = NLPManager()

    @classmethod
    def add_plugin(cls, module_path: str, plugin: Plugin) -> None:
        """Register a plugin
        
        Args:
            module_path (str): module path
            plugin (Plugin): Plugin object
        """
        if module_path in cls._plugins:
            warnings.warn(f"Plugin {module_path} already exists")
            return
        cls._plugins[module_path] = plugin

    @classmethod
    def get_plugin(cls, module_path: str) -> Optional[Plugin]:
        """Get plugin object by plugin module path
        
        Args:
            module_path (str): Plugin module path
        
        Returns:
            Optional[Plugin]: Plugin object
        """
        return cls._plugins.get(module_path, None)

    @classmethod
    def remove_plugin(cls, module_path: str) -> bool:
        """Remove a plugin by plugin module path
        
        ** Warning: This function not remove plugin actually! **
        ** Just remove command, nlprocessor, event handlers **
        ** and message preprocessors, and deletes it from PluginManager **

        Args:
            module_path (str): Plugin module path

        Returns:
            bool: Success or not
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not exists")
            return False
        for command in plugin.commands:
            CommandManager.remove_command(command.name)
        for nl_processor in plugin.nl_processors:
            NLPManager.remove_nl_processor(nl_processor)
        for event_handler in plugin.event_handlers:
            EventManager.remove_event_handler(event_handler)
        from .message import MessagePreprocessorManager  # avoid import cycles
        for msg_preprocessor in plugin.msg_preprocessors:
            MessagePreprocessorManager.remove_message_preprocessor(msg_preprocessor)
        del cls._plugins[module_path]
        return True

    @classmethod
    def switch_plugin_global(cls,
                             module_path: str,
                             state: Optional[bool] = None) -> None:
        """Change plugin state globally or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for command in plugin.commands:
            CommandManager.switch_command_global(command.name, state)
        for nl_processor in plugin.nl_processors:
            NLPManager.switch_nlprocessor_global(nl_processor, state)
        for event_handler in plugin.event_handlers:
            EventManager.switch_event_handler_global(event_handler, state)
        from .message import MessagePreprocessorManager  # avoid import cycles
        for msg_preprocessor in plugin.msg_preprocessors:
            MessagePreprocessorManager.switch_message_preprocessor_global(msg_preprocessor, state)

    @classmethod
    def switch_command_global(cls,
                              module_path: str,
                              state: Optional[bool] = None) -> None:
        """Change plugin command state globally or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for command in plugin.commands:
            CommandManager.switch_command_global(command.name, state)

    @classmethod
    def switch_nlprocessor_global(cls,
                                  module_path: str,
                                  state: Optional[bool] = None) -> None:
        """Change plugin nlprocessor state globally or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for processor in plugin.nl_processors:
            NLPManager.switch_nlprocessor_global(processor, state)

    @classmethod
    def switch_eventhandler_global(cls,
                                   module_path: str,
                                   state: Optional[bool] = None) -> None:
        """Change plugin event handler state globally or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for event_handler in plugin.event_handlers:
            EventManager.switch_event_handler_global(event_handler, state)

    @classmethod
    def switch_messagepreprocessor_global(cls,
                                          module_path: str,
                                          state: Optional[bool] = None) -> None:
        """Change plugin message preprocessor state globally or simply switch it if `state`
        is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = cls.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        from .message import MessagePreprocessorManager  # avoid import cycles
        for msg_preprocessor in plugin.msg_preprocessors:
            MessagePreprocessorManager.switch_message_preprocessor_global(msg_preprocessor, state)

    def switch_plugin(self,
                      module_path: str,
                      state: Optional[bool] = None) -> None:
        """Change plugin state or simply switch it if `state` is None
        
        Tips:
            This method will only change the state of the plugin's
            commands and natural language processors since changing
            state of the event handler for message and changing other message
            preprocessors are meaningless (needs discussion).
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = self.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for command in plugin.commands:
            self.cmd_manager.switch_command(command.name, state)
        for nl_processor in plugin.nl_processors:
            self.nlp_manager.switch_nlprocessor(nl_processor, state)

    def switch_command(self,
                       module_path: str,
                       state: Optional[bool] = None) -> None:
        """Change plugin command state or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = self.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for command in plugin.commands:
            self.cmd_manager.switch_command(command.name, state)

    def switch_nlprocessor(self,
                           module_path: str,
                           state: Optional[bool] = None) -> None:
        """Change plugin nlprocessor state or simply switch it if `state` is None
        
        Args:
            module_path (str): Plugin module path
            state (Optional[bool]): State to change to. Defaults to None.
        """
        plugin = self.get_plugin(module_path)
        if not plugin:
            warnings.warn(f"Plugin {module_path} not found")
            return
        for processor in plugin.nl_processors:
            self.nlp_manager.switch_nlprocessor(processor, state)


def _add_handlers_to_managers():
    for cmd, aliases, patterns in Plugin.GlobalTemp.commands:
        CommandManager.add_command(cmd.name, cmd)
        # TODO: skip when command exists
        CommandManager.add_aliases(aliases, cmd)
        CommandManager.add_patterns(patterns, cmd)
    for processor in Plugin.GlobalTemp.nl_processors:
        NLPManager.add_nl_processor(processor)
    for handler in Plugin.GlobalTemp.event_handlers:
        EventManager.add_event_handler(handler)
    from .message import MessagePreprocessorManager  # avoid import cycles
    for mp in Plugin.GlobalTemp.msg_preprocessors:
        MessagePreprocessorManager.add_message_preprocessor(mp)


def load_plugin(module_path: str) -> Optional[Plugin]:
    """Load a module as a plugin
    
    Args:
        module_path (str): path of module to import
    
    Returns:
        Optional[Plugin]: Plugin object loaded
    """
    try:
        with Plugin.GlobalTemp.enter_plugin():
            module = importlib.import_module(module_path)
        plugin = Plugin.GlobalTemp.make_plugin(module)

        # at this point, GlobalTemp and plugin object ^ have same contents
        _add_handlers_to_managers()

        PluginManager.add_plugin(module_path, plugin)
        logger.info(f'Succeeded to import "{module_path}"')
        return plugin
    except Exception as e:
        logger.error(f'Failed to import "{module_path}", error: {e}')
        logger.exception(e)
        return None


def unload_plugin(module_path: str) -> bool:
    """Unloads a plugin.

    This deletes its entry in sys.modules if present. However, if the module
    had additional side effects other than defining processors, they are not
    undone.
    
    Args:
        module_path (str): import path to module, which is already imported

    Returns:
        bool: Plugin successfully unloaded
    """
    result = PluginManager.remove_plugin(module_path)
    if result:
        for module in [m for m in sys.modules.keys() if m.startswith(module_path)]:
            del sys.modules[module]
        logger.info(f'Succeeded to unload "{module_path}"')
    return result


def reload_plugin(module_path: str) -> Optional[Plugin]:
    if not unload_plugin(module_path):  # the one more mysterious log info seems valid..
        return None

    try:
        with Plugin.GlobalTemp.enter_plugin():
            # NOTE: consider importlib.reload()
            module = importlib.import_module(module_path)
        plugin = Plugin.GlobalTemp.make_plugin(module)

        _add_handlers_to_managers()

        PluginManager.add_plugin(module_path, plugin)
        logger.info(f'Succeeded to reload "{module_path}"')
        return plugin
    except Exception as e:
        logger.error(f'Failed to reload "{module_path}", error: {e}')
        logger.exception(e)
        return None


def load_plugins(plugin_dir: str, module_prefix: str) -> Set[Plugin]:
    """Find all non-hidden modules or packages in a given directory,
    and import them with the given module prefix.

    Args:
        plugin_dir (str): Plugin directory to search
        module_prefix (str): Module prefix used while importing

    Returns:
        Set[Plugin]: Set of plugin objects successfully loaded
    """

    count = set()
    for name in os.listdir(plugin_dir):
        path = os.path.join(plugin_dir, name)
        if os.path.isfile(path) and \
                (name.startswith('_') or not name.endswith('.py')):
            continue
        if os.path.isdir(path) and \
                (name.startswith('_') or not os.path.exists(
                    os.path.join(path, '__init__.py'))):
            continue

        m = re.match(r'([_A-Z0-9a-z]+)(.py)?', name)
        if not m:
            continue

        result = load_plugin(f'{module_prefix}.{m.group(1)}')
        if result:
            count.add(result)
    return count


def load_builtin_plugins() -> Set[Plugin]:
    """
    Load built-in plugins distributed along with "nonebot" package.
    """
    plugin_dir = os.path.join(os.path.dirname(__file__), 'plugins')
    return load_plugins(plugin_dir, 'nonebot.plugins')


def get_loaded_plugins() -> Set[Plugin]:
    """
    Get all plugins loaded.

    :return: a set of Plugin objects
    """
    return set(PluginManager._plugins.values())


def on_command(
    name: Union[str, CommandName_T],
    *,
    aliases: Union[Iterable[str], str] = (),
    patterns: Patterns_T = (),
    permission: Union[PermissionPolicy_T, Iterable[PermissionPolicy_T]] = ...,
    only_to_me: bool = True,
    privileged: bool = False,
    shell_like: bool = False,
    expire_timeout: Optional[timedelta] = ...,
    run_timeout: Optional[timedelta] = ...,
    session_class: Optional[Type[CommandSession]] = None
) -> Callable[[CommandHandler_T], CommandHandler_T]:
    """
    Decorator to register a function as a command.

    :param name: command name (e.g. 'echo' or ('random', 'number'))
    :param aliases: aliases of command name, for convenient access
    :param patterns: custom regex pattern for the command.
           Please use this carefully. Abuse may cause performance problem.
           Also, Please notice that if a message is matched by this method,
           it will use the full command as session current_arg.
    :param permission: permission required by the command
    :param only_to_me: only handle messages to me
    :param privileged: can be run even when there is already a session
    :param shell_like: use shell-like syntax to split arguments
    :param expire_timeout: will override SESSION_EXPIRE_TIMEOUT if provided
    :param run_timeout: will override SESSION_RUN_TIMEOUT if provided
    :param session_class: session class
    """
    real_permission = perm.aggregate_policy(permission) \
        if isinstance(permission, Iterable) else permission

    def deco(func: CommandHandler_T) -> CommandHandler_T:
        if not isinstance(name, (str, tuple)):
            raise TypeError('the name of a command must be a str or tuple')
        if not name:
            raise ValueError('the name of a command must not be empty')
        if session_class is not None and not issubclass(session_class,
                                                        CommandSession):
            raise TypeError(
                'session_class must be a subclass of CommandSession')

        cmd_name = (name,) if isinstance(name, str) else name

        cmd = Command(name=cmd_name,
                      func=func,
                      only_to_me=only_to_me,
                      privileged=privileged,
                      permission=real_permission,
                      expire_timeout=expire_timeout,
                      run_timeout=run_timeout,
                      session_class=session_class)

        if shell_like:

            async def shell_like_args_parser(session: CommandSession):
                session.state['argv'] = shlex.split(session.current_arg) if \
                    session.current_arg else []

            cmd.args_parser_func = shell_like_args_parser

        if Plugin.GlobalTemp.now_within_plugin:
            Plugin.GlobalTemp.commands.append((cmd, aliases, patterns))
        else:
            CommandManager.add_command(cmd_name, cmd)
            CommandManager.add_aliases(aliases, cmd)
            CommandManager.add_patterns(patterns, cmd)
            warnings.warn('defining command_handler outside a plugin is deprecated '
                          'and will not be supported in the future')

        func.args_parser = cmd.args_parser

        return func

    return deco


@overload
def on_natural_language(__func: NLPHandler_T) -> NLPHandler_T:
    """
    Decorator to register a function as a natural language processor with
    default kwargs.
    """


@overload
def on_natural_language(
    keywords: Optional[Union[Iterable[str], str]] = ...,
    *,
    permission: Union[PermissionPolicy_T, Iterable[PermissionPolicy_T]] = ...,
    only_to_me: bool = ...,
    only_short_message: bool = ...,
    allow_empty_message: bool = ...
) -> Callable[[NLPHandler_T], NLPHandler_T]:
    """
    Decorator to register a function as a natural language processor.

    :param keywords: keywords to respond to, if None, respond to all messages
    :param permission: permission required by the processor
    :param only_to_me: only handle messages to me
    :param only_short_message: only handle short messages
    :param allow_empty_message: handle empty messages
    """


def on_natural_language(
    keywords: Union[Optional[Iterable[str]], str, NLPHandler_T] = None,
    *,
    permission: Union[PermissionPolicy_T, Iterable[PermissionPolicy_T]] = ...,
    only_to_me: bool = True,
    only_short_message: bool = True,
    allow_empty_message: bool = False
):
    """
    Implementation of on_natural_language overloads.
    """
    real_permission = perm.aggregate_policy(permission) \
        if isinstance(permission, Iterable) else permission

    def deco(func: NLPHandler_T) -> NLPHandler_T:
        nl_processor = NLProcessor(
            func=func,
            keywords=keywords,  # type: ignore
            only_to_me=only_to_me,
            only_short_message=only_short_message,
            allow_empty_message=allow_empty_message,
            permission=real_permission)

        if Plugin.GlobalTemp.now_within_plugin:
            Plugin.GlobalTemp.nl_processors.add(nl_processor)
        else:
            NLPManager.add_nl_processor(nl_processor)
            warnings.warn('defining nl_processor outside a plugin is deprecated '
                          'and will not be supported in the future')
        return func

    if callable(keywords):
        # here "keywords" is the function to be decorated
        # applies default args provided by this function
        return on_natural_language()(keywords)
    else:
        if isinstance(keywords, str):
            keywords = (keywords,)
        return deco


_Teh = TypeVar('_Teh', NoticeHandler_T, RequestHandler_T)


def _make_event_deco(post_type: str):

    def deco_deco(arg: Optional[Union[str, _Teh]] = None,
                  *events: str) -> Union[Callable[[_Teh], _Teh], _Teh]:

        def deco(func: _Teh) -> _Teh:
            if isinstance(arg, str):
                events_tmp = list(
                    map(lambda x: f"{post_type}.{x}", [arg, *events]))  # if arg is part of events str
                handler = EventHandler(events_tmp, func)
            else:
                handler = EventHandler([post_type], func)

            if Plugin.GlobalTemp.now_within_plugin:
                Plugin.GlobalTemp.event_handlers.add(handler)
            else:
                EventManager.add_event_handler(handler)
                warnings.warn('defining event_handler outside a plugin is deprecated '
                              'and will not be supported in the future')
            return func

        if callable(arg):
            return deco(arg)
        return deco

    return deco_deco


@overload
def on_notice(__func: NoticeHandler_T) -> NoticeHandler_T: ...  # type: ignore


@overload
def on_notice(*events: str) -> Callable[[NoticeHandler_T], NoticeHandler_T]: ...


on_notice = _make_event_deco('notice')  # type: ignore[override]


@overload
def on_request(__func: RequestHandler_T) -> RequestHandler_T: ...  # type: ignore


@overload
def on_request(*events: str) -> Callable[[RequestHandler_T], RequestHandler_T]: ...


on_request = _make_event_deco('request')  # type: ignore[override]


__all__ = [
    'Plugin',
    'PluginManager',
    'load_plugin',
    'unload_plugin',
    'reload_plugin',
    'load_plugins',
    'load_builtin_plugins',
    'get_loaded_plugins',
    'on_command',
    'on_natural_language',
    'on_notice',
    'on_request',
]
