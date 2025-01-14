from django.shortcuts import render, redirect
from django.contrib.auth import authenticate
from django.contrib import auth
from appMesaServicio.models import *
from random import *
from django.db import Error, transaction
from datetime import datetime
# para correo
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
import threading
from smtplib import SMTPException
from django.http import JsonResponse

# Create your views here.


def inicio(request):
    return render(request, "frmIniciarSesion.html")


def inicioAdministrador(request):
    if request.user.is_authenticated:
        datosSesion = {"user": request.user,
                       "rol": request.user.groups.get().name}
        return render(request, "administrador/inicio.html", datosSesion)
    else:
        mensaje = "Debe iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def inicioTecnico(request):
    if request.user.is_authenticated:
        datosSesion = {"user": request.user,
                       "rol": request.user.groups.get().name}
        return render(request, "tecnico/inicio.html", datosSesion)
    else:
        mensaje = "Debe iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def inicioEmpleado(request):
    if request.user.is_authenticated:
        datosSesion = {"user": request.user,
                       "rol": request.user.groups.get().name}
        return render(request, "empleado/inicio.html", datosSesion)
    else:
        mensaje = "Debe iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def login(request):
    username = request.POST["txtUser"]
    password = request.POST["txtPassword"]
    user = authenticate(username=username, password=password)
    if user is not None:
        # registrar la variable de sesión
        auth.login(request, user)
        if user.groups.filter(name='Administrador').exists():
            return redirect('/inicioAdministrador')
        elif user.groups.filter(name='Tecnico').exists():
            return redirect('/inicioTecnico')
        else:
            return redirect('/inicioEmpleado')
    else:
        mensaje = "Usuario o Contraseña Incorrectas"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def vistaSolicitud(request):
    if request.user.is_authenticated:
        # consultar las oficinas y ambientes registrados
        oficinaAmbientes = OficinaAmbiente.objects.all()
        datosSesion = {"user": request.user,
                       "rol": request.user.groups.get().name,
                       'oficinasAmbientes': oficinaAmbientes}
        return render(request, 'empleado/solicitud.html', datosSesion)
    else:
        mensaje = "Debe iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def registrarSolicitud(request):
    """_summary_
        Función que realiza el proceso de registrar
        la solicitud por parte del empleado
    Args:
        request (_type_): objeto con la descripción, la
        oficina y el empleado que hace la solicitud

    Returns:
        _type_: mensaje de registro o no de la solicitud
    """
    if request.user.is_authenticated:
        try:
            with transaction.atomic():
                user = request.user
                descripcion = request.POST['txtDescripcion']
                idOficinaAmbiente = int(request.POST['cbOficinaAmbiente'])
                oficinaAmbiente = OficinaAmbiente.objects.get(
                    pk=idOficinaAmbiente)
                solicitud = Solicitud(solUsuario=user, solDescripcion=descripcion,
                                      solOficinaAmbiente=oficinaAmbiente)
                solicitud.save()
                # obtener año para en el consecutivo agregar el año.
                fecha = datetime.now()
                year = fecha.year
                # obtener el número de solicitudes hechas por año actual
                consecutivoCaso = Solicitud.objects.filter(
                    fechaHoraCreacion__year=year).count()
                # ajustar el consecutivon con ceros a las izquierda
                consecutivoCaso = str(consecutivoCaso).rjust(5, '0')
                # crear el código del caso formato REQ-AÑOVIGENCIA-CONSECUTIVO
                codigoCaso = f"REQ-{year}-{consecutivoCaso}"
                # consultar el usuario tipo Administrador para asignarlo al caso
                userCaso = User.objects.filter(
                    groups__name__in=['Administrador']).first()
                # crear el caso
                caso = Caso(casSolicitud=solicitud,
                            casCodigo=codigoCaso, casUsuario=userCaso)
                caso.save()
                # enviar el correo al empleado
                asunto = 'Registro Solicitud - Mesa de Servicio - CTPI-CAUCA'
                mensajeCorreo = f'Cordial saludo, <b>{user.first_name} {user.last_name}</b>, nos permitimos \
                    informarle que su solicitud fue registrada en nuestro sistema con el número de caso \
                    <b>{codigoCaso}</b>. <br><br> Su caso será gestionado en el menor tiempo posible, \
                    según los acuerdos de solución establecidos para la Mesa de Servicios del CTPI-CAUCA.\
                    <br><br>Lo invitamos a ingresar a nuestro sistema en la siguiente url:\
                    http://mesadeservicioctpicauca.sena.edu.co.'
                # crear el hilo para el envío del correo
                thread = threading.Thread(
                    target=enviarCorreo, args=(asunto, mensajeCorreo, [user.email]))
                # ejecutar el hilo
                thread.start()
                mensaje = "Se ha registrado su solicitud de manera exitosa"
        except Error as error:
            transaction.rollback()
            mensaje = f"{error}"

        oficinaAmbientes = OficinaAmbiente.objects.all()
        retorno = {"mensaje": mensaje, "oficinasAmbientes": oficinaAmbientes}
        return render(request, "empleado/solicitud.html", retorno)
    else:
        mensaje = "Debe primero iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def enviarCorreo(asunto=None, mensaje=None, destinatario=None, archivo=None):
    remitente = settings.EMAIL_HOST_USER
    template = get_template('enviarCorreo.html')
    contenido = template.render({
        'mensaje': mensaje,
    })
    try:
        correo = EmailMultiAlternatives(
            asunto, mensaje, remitente, destinatario)
        correo.attach_alternative(contenido, 'text/html')
        if archivo != None:
            correo.attach_file(archivo)
        correo.send(fail_silently=True)
    except SMTPException as error:
        print(error)


def listarCasos(request):
    """_summary_
        obtiene los casos en estado solicitada
        y los empleados técnicos para asignar a 
        los casos.
    Args:
        request (_type_): _description_

    Returns:
        _type_: Lista de los casos y de los empleados técnicos
    """
    if request.user.is_authenticated:
        try:
            mensaje = ""
            fecha = datetime.now()
            year = fecha.year
            listaCasos = Caso.objects.filter(
                casSolicitud__fechaHoraCreacion__year=year, casEstado='Solicitada')
            tecnicos = User.objects.filter(groups__name__in=['Tecnico'])
        except Error as error:
            mensaje = str(error)
        retorno = {"listaCasos": listaCasos,
                   "tecnicos": tecnicos, "mensaje": mensaje}
        return render(request, "administrador/listarCasos.html", retorno)
    else:
        mensaje = "Debe primero iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def listarEmpleadosTecnicos(request):
    if request.user.is_authenticated:
        try:
            mensaje = ""
            # consulta para obtener todos los empleados con rol Tecnico
            tecnicos = User.objects.filter(groups__name__in=['Tecnico'])
        except Error as error:
            mensaje = str(error)
        retorno = {"tecnicos": tecnicos, 'mensaje': mensaje}
        return JsonResponse(retorno)
    else:
        mensaje = "Debe primero iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def asignarTecnicoCaso(request):
    if request.user.is_authenticated:
        try:
            idTecnico = int(request.POST['cbTecnico'])
            userTecnico = User.objects.get(pk=idTecnico)
            idCaso = int(request.POST['idCaso'])
            caso = Caso.objects.get(pk=idCaso)
            caso.casUsuario = userTecnico
            caso.casEstado = "En Proceso"
            caso.save()
            # enviar correo al técnico
            asunto = 'Asignación Caso - Mesa de Servicio - CTPI-CAUCA'
            mensajeCorreo = f'Cordial saludo, <b>{userTecnico.first_name} {userTecnico.last_name}</b>, nos permitimos \
                    informarle que se le ha asignado un caso para dar solución. Código de Caso:  \
                    <b>{caso.casCodigo}</b>. <br><br> Se solicita se atienda de manera oportuna \
                    según los acuerdos de solución establecidos para la Mesa de Servicios del CTPI-CAUCA.\
                    <br><br>Lo invitamos a ingresar al sistema para gestionar sus casos asignados en la siguiente url:\
                    http://mesadeservicioctpicauca.sena.edu.co.'
            # crear el hilo para el envío del correo
            thread = threading.Thread(
                target=enviarCorreo, args=(asunto, mensajeCorreo, [userTecnico.email]))
            # ejecutar el hilo
            thread.start()
            mensaje = "Caso asignado"
        except Error as error:
            mensaje = str(error)
        return redirect('/listarCasosParaAsignar/')
    else:
        mensaje = "Debe primero iniciar sesión"
        return render(request, "frmIniciarSesion.html", {"mensaje": mensaje})


def listarCasoAsignadosTecnico(request):
    if request.user.is_authenticated:
        
        try:
            listaCaso = Caso.objects.filter(casEstado='En Proceso', casUsuario=request.user)
            listaTipoProcedimiento = TipoProcedimiento.objects.all().values()
            mensaje = "listado de casos asignados"
        except Error as error:
            mensaje = str(error)
            
        retorno = {'mensaje':mensaje,'ListaCasos':listaCaso,'listaTipoSolucion':tipoSolucion,'listaTipoProcedimiento': listaTipoProcedimiento}
        
        return render(request,"tecnico/listarCasosAsignados.html", retorno)
    else:
        mensaje = "debe iniciar sesion"
        return render(request,"frmIniciarSesion.html",{"mensaje":mensaje})
        
    
def solucionCaso(request):
    if request.user.is_authenticated:
        procedimiento = request.POST['txtProcedimiento']        
        TipoProc = int(request.POST['cbTipoProcedimiento'])
        TipoProcedimiento = TipoProcedimiento.objects.get(pk=TipoProc)
        tipoSolucion = request.POST['cbTipoSolucion']
        idCaso = Caso.objects.get(pk=idCaso)
        solucionCaso = solucionCaso(solCaso=Caso,solProcedimiento=procedimiento,solTipoSolucion=tipoSolucion)
        
        solucionCaso.save()
        
        
        if(tipoSolucion=="definitiva"):
            Caso.casEstado = 'finalizada'
            Caso.save()
            
        
        
        SolucionCasoTipoProcedimientos = SolucionCasoTipoProcedimientos(solSolucionCaso = solucionCaso,solTipoProcedimineto=TipoProcedimiento)
        
        SolucionCasoTipoProcedimientos.save()
        
    else:
        pass



def salir(request):
    auth.logout(request)
    return render(request, "frmIniciarSesion.html",
                  {"mensaje": "Ha cerrado la sesión"})




def estadisticas(request):
    if request.user.is_authenticated:
        listarAmbientes = OficinaAmbiente.objects.get
        
        
        textprops = {'fontsize': 6}
        plt.title("cantidad fr dolicitudes realizadas \n por ambiente")

