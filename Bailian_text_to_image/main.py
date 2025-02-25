from http import HTTPStatus
from urllib.parse import urlparse, unquote
from pathlib import PurePosixPath
import requests
import asyncio
import re
import dashscope
from dashscope import ImageSynthesis
from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from plugins.LangBot_BailianTextToImagePlugin.config import Config
import pkg.platform.types as platform_types  # 导入 platform_types
import os

# 注册插件
@register(name="LangBot_BailianTextToImagePlugin", description="调用阿里云百炼平台文生图API生成图片。", version="1.0", author="Thetail")
class TextToImage(BasePlugin):

    # 插件加载时触发
    def __init__(self, host: APIHost):
        super().__init__(host)

    # 异步初始化
    async def initialize(self):
        pass

    # 当收到消息时触发
    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def on_message(self, ctx: EventContext):
        await self.process_message(ctx)

    async def process_message(self, ctx: EventContext):
        """处理收到的消息"""
        message_chain = ctx.event.query.message_chain
        self.ap.logger.info(f"message_chain: {message_chain}")
        for message in message_chain:
            if isinstance(message, platform_types.Plain):
                if re.search("画图", message.text):  # 检测是否包含 "/ig" 或 "／ig"
                    prompt = re.split("画图", message.text, 1)[-1].strip()  # 按 "/ig" 或 "／ig" 分割，并获取后面的部分
                    print(prompt)
                    message_parts = await self.process_command(ctx, prompt)
                    ctx.add_return('reply', message_parts)
                    ctx.prevent_default()
                    ctx.prevent_postorder()
                    break

    async def process_command(self, ctx: EventContext, input_prompt: str):
        try:
            # 第一步：发起异步请求，获取任务 ID
            model = Config.model
            size = Config.size
            dashscope.api_key = Config.DASHSCOPE_API_KEY
            rsp = ImageSynthesis.async_call(api_ley=Config.DASHSCOPE_API_KEY,
                                            model=model,
                                            prompt=input_prompt,
                                            n=1,
                                            size=size)

            # print(f"rsp: {rsp}")
            if rsp.status_code != HTTPStatus.OK:
                self.ap.logger.error(f"Failed to start task: {rsp.code}, message: {rsp.message}")
                return f"Failed to start task: {rsp.code}, message: {rsp.message}"

            # 第二步：轮询等待任务完成
            while True:
                await asyncio.sleep(2)  # 等待一段时间后再查询状态，避免频繁请求服务器

                status_rsp = ImageSynthesis.fetch(rsp)
                print(status_rsp)

                if status_rsp.status_code != HTTPStatus.OK:
                    self.ap.logger.error(f"Failed to fetch task status: {status_rsp.code}, message: {status_rsp.message}")
                    return f"Failed to fetch task status: {status_rsp.code}, message: {status_rsp.message}"
                
                if status_rsp.output.task_status == 'SUCCEEDED':
                    break   # 图片生成成功，跳出循环
                
                elif status_rsp.output.task_status in ['FAILED', 'CANCELED']:
                    self.ap.logger.error(f"Task failed with status: {status_rsp.output.task_status}")
                    return f"Task failed with status: {status_rsp.output.task_status}"

            # 第三步：获取最终结果
            final_rsp = ImageSynthesis.wait(rsp)

            if final_rsp.status_code == HTTPStatus.OK:
                url = final_rsp.output.results[0]["url"]
                
                folder_name = "tmp_photo"
                file_name = "tmp_photo.png"
                
                current_dir = os.path.dirname(os.path.abspath(__file__))
                target_folder = os.path.join(current_dir, folder_name)
                os.makedirs(target_folder, exist_ok=True)
                
                file_path = os.path.join(target_folder, file_name)

                response = requests.get(url, timeout=10)
                response.raise_for_status()  # 检查 HTTP 错误
               
                with open(file_path, "wb") as f:
                    f.write(response.content)
               
                
                # print(f"photo url: {url}")
                return f"请将以下链接复制到浏览器中打开：{url}" 
               
                message_parts = [platform_types.Image(url=url)]
                # return message_parts
            
            else:
                self.ap.logger.error(f'Failed to retrieve image: {final_rsp.code}, message: {final_rsp.message}')
                return f'Failed to retrieve image: {final_rsp.code}, message: {final_rsp.message}'

        except Exception as e:
            self.ap.logger.error(f"生成图片异常: {e}")

    # 插件卸载时触发
    def __del__(self):
        pass